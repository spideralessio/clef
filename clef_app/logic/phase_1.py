import datetime
from typing import List, Dict
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool
from clef_app.config import ConfigManager
from clef_app.llm_provider import get_llm
from clef_app.database import DatabaseManager
from clef_app.tools import DownloadPageTool, SaveArticleTool

class Phase1Runner:
    def __init__(self):
        self.config = ConfigManager()
        self.llm = get_llm()
        self.db = DatabaseManager()
        
    def run(self, selected_sources: List[str] = None, logger_callback=None):
        def log(msg):
            if logger_callback:
                logger_callback(msg)
            # We also keep building the result dict for return consistency, though less useful now
            # results[journal_name] += msg + "\n" # This is tricky if we don't know journal_name globally
            # Let's just use log for side effects and return a simple summary.
            
        sources = self.config.get("sources", {})
        if selected_sources:
            sources = {k: v for k, v in sources.items() if k in selected_sources}
            
        prompts = self.config.get("prompts", {})
        settings = self.config.get("settings", {})
        max_rpm = settings.get("max_rpm", 10)
        
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        # Tools
        scrape_tool = ScrapeWebsiteTool()
        download_tool = DownloadPageTool()
        save_tool = SaveArticleTool()
        
        # 1. Article List Extractor Agent
        article_finder_agent = Agent(
            role="Article List Extractor",
            goal="Extract a complete list of articles from a journal page with their titles and URLs.",
            backstory=prompts.get("search_articles", "You are a precise article finder..."),
            verbose=True,
            llm=self.llm,
            max_rpm=max_rpm,
            allow_delegation=False,
            # tools=[download_tool] # ScrapeWebsiteTool might be better if download_tool is just HTML
            tools=[scrape_tool, download_tool] 
        )

        # 2. Article Content Processor Agent (MOVED INSIDE LOOP)
        # article_processor_agent = Agent(...) 

        results = {}

        for journal_name, url in sources.items():
            # results[journal_name] = f"Processing {journal_name}...\n"
            log(f"Processing {journal_name}...")
            
            # --- Step 1: Find Articles ---
            find_articles_task = Task(
                description=(
                    f"Visit the '{journal_name}' at {url} and extract ALL articles.\n"
                    "Return a structured list containing:\n"
                    "- Article title\n"
                    "- Article URL\n"
                    "Format the output as a clear, numbered list. Example:\n"
                    "1. Title: 'Example Article' | URL: 'https://example.com/article1'\n"
                    "2. Title: 'Another Article' | URL: 'https://example.com/article2'\n"
                    "Be thorough and include ALL articles."
                ),
                expected_output="A complete numbered list of all articles from likely recent posts.",
                agent=article_finder_agent
            )

            finder_crew = Crew(
                agents=[article_finder_agent],
                tasks=[find_articles_task],
                process=Process.sequential,
                verbose=True
            )

            try:
                finder_result = finder_crew.kickoff()
                log(f"[{journal_name}] Found articles list. Parsing...")
                
                # Parse links from the result text (LLM output)
                # Simple regex or line splitting as per script
                result_str = str(finder_result)
                article_info_list = []
                lines = result_str.split('\n')
                for line in lines:
                    if 'http' in line: 
                        article_info_list.append(line.strip())
                
                log(f"[{journal_name}] Extracted {len(article_info_list)} items.")

                # --- Step 2: Process Each Article ---
                import re
                for idx, info in enumerate(article_info_list):
                    # Extract URL to check existence
                    url_match = re.search(r'https?://[^\s\'")]+', info)
                    if url_match:
                        found_url = url_match.group(0)
                        # Clean trailing punctuation often caught if regex is simple
                        found_url = found_url.rstrip(",.;")
                        
                        if self.db.article_exists(found_url):
                            log(f"[{journal_name}] Skipping existing article ({idx+1}/{len(article_info_list)}): {found_url}")
                            continue

                    log(f"[{journal_name}] Processing {idx+1}/{len(article_info_list)}: {info[:50]}...")
                    
                    # Create a FRESH agent for each article to avoid context accumulation
                    article_processor_agent = Agent(
                        role="Article Content Processor",
                        goal="Scrape, summarize, categorize, and save a single article's content with complete metadata.",
                        backstory=prompts.get("process_articles", "You are a meticulous content processor..."),
                        verbose=True,
                        llm=self.llm,
                        max_rpm=max_rpm,
                        allow_delegation=False,
                        # memory=False, # Ensure no memory is retained
                        tools=[download_tool, save_tool] 
                    )

                    process_task = Task(
                        description=(
                            f"Process the following article from '{journal_name}':\n"
                            f"{info}\n\n"
                            "Perform these steps IN ORDER:\n"
                            "1. Scrape the article webpage to extract the full plain text content.\n"
                            f"   CONTEXT: Today is {today_str}. If the publication date is missing or relative (like '2 hours ago'), calculate the correct date.\n"
                            "2. Generate a concise summary (2-3 sentences).\n"
                            "3. Determine the article category and music style.\n"
                            "4. Extract title, URL, publication date.\n"
                            "5. Create a URL-friendly slug.\n"
                            "6. Use the Save Article Tool with metdata.\n"
                            f"IMPORTANT: The date defaults to today ({today_str}) if not found."
                        ),
                        expected_output="Confirmation that article is saved.",
                        agent=article_processor_agent
                    )
                    
                    processor_crew = Crew(
                        agents=[article_processor_agent],
                        tasks=[process_task],
                        process=Process.sequential,
                        verbose=True
                    )
                    
                    try:
                        processor_crew.kickoff()
                        log(f"[{journal_name}] Processed item {idx+1}")
                    except Exception as e:
                        log(f"[{journal_name}] Error processing item {idx+1}: {e}")
                        
            except Exception as e:
                log(f"[{journal_name}] Error in finding phase: {str(e)}")
                
        return results
