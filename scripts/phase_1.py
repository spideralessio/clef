import os
import json
from datetime import datetime
import re
from crewai import Agent, Task, Crew, Process
from crewai_tools import ScrapeWebsiteTool
from crewai.tools import BaseTool
from scraper_tool import DownloadPageTool

from dotenv import load_dotenv

load_dotenv()

from llm import LLM

llm = LLM(model="openai/gpt-4.1", temperature=0.1,
          max_tokens=5000)  # Reduced temperature for determinism

# --- Journal & Tool Configuration ---

journals = {
    'Rolling Stone Italy': 'https://www.rollingstone.it/musica/feed/',
    'Rolling Stone USA': 'https://www.rollingstone.com/music/feed/',
}

article_categories = [
    'music', 'culture', 'reviews', 'journeys/itineraries/music-trips',
    'interviews', 'education'
]

music_styles = [
    'uncategorized', 'classical', 'electronic', 'folk', 'hip-hop', 'jazz',
    'metal', 'pop', 'rock', 'world-music'
]


def slugify(text):
    """
    Creates a URL-friendly 'slug' from a given text string.
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text


# --- Custom Tool for Saving Articles ---


class SaveArticleTool(BaseTool):
    name: str = "Save Article Tool"
    description: str = "Saves an article's plain text content and metadata to the local filesystem."

    def _run(self, journal_name: str, article_date: str, slug: str,
             text_content: str, metadata: dict) -> str:
        """
        Saves the article's plain text content and metadata into the specified directory structure.
        """
        base_dir = 'articles'
        try:
            journal_slug = slugify(journal_name)
            article_path = os.path.join(base_dir, journal_slug, article_date,
                                        slug)
            os.makedirs(article_path, exist_ok=True)

            # Save plain text content to a .txt file
            with open(os.path.join(article_path, 'content.txt'),
                      'w',
                      encoding='utf-8') as f:
                f.write(text_content)

            # Save metadata to a .json file
            with open(os.path.join(article_path, 'metadata.json'),
                      'w',
                      encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)

            return f"Successfully saved article '{slug}' for journal '{journal_name}'."
        except Exception as e:
            return f"Error saving article '{slug}': {e}"


# --- Agent and Task Definitions ---

scrape_tool = ScrapeWebsiteTool()
download_tool = DownloadPageTool()
save_tool = SaveArticleTool()

# Article List Extractor Agent - focused solely on finding articles
article_finder_agent = Agent(
    role="Article List Extractor",
    goal=
    "Extract a complete list of articles from a journal page with their titles and URLs.",
    backstory=
    "You are a precise article finder. Your sole responsibility is to visit a journal page, "
    "identify all articles published, and return a structured list with exact titles and URLs. "
    "You do NOT process the articles themselves.",
    verbose=True,
    inject_date=True,
    llm=llm,
    allow_delegation=False,  # No delegation - focused task
    tools=[download_tool])

# Article Content Processor Agent - processes individual articles
article_processor_agent = Agent(
    role="Article Content Processor",
    goal=
    "Scrape, summarize, categorize, and save a single article's content with complete metadata.",
    backstory=
    "You are a meticulous content processor. For each article URL provided to you, you scrape the full text, "
    "generate a concise summary, determine the category and music style, extract metadata, and save everything.",
    verbose=True,
    inject_date=True,
    llm=llm,
    allow_delegation=False,  # No delegation - sequential processing
    tools=[scrape_tool, save_tool])

# --- Main Execution Logic ---


def process_journal(journal_name: str, journal_url: str) -> dict:
    """
    Process a single journal: find articles, then process each one sequentially.
    Returns a summary of the processing results.
    """
    today_str = datetime.now().strftime('%Y-%m-%d')

    print(f"\n{'='*60}")
    print(f"Processing Journal: {journal_name}")
    print(f"{'='*60}\n")

    # STEP 1: Find all today's articles
    find_articles_task = Task(
        description=
        (f"Visit the '{journal_name}' at {journal_url} and extract ALL articles.\n"
         "Return a structured list containing:\n"
         "- Article title\n"
         "- Article URL\n"
         "Format the output as a clear, numbered list. Example:\n"
         "1. Title: 'Example Article' | URL: 'https://example.com/article1'\n"
         "2. Title: 'Another Article' | URL: 'https://example.com/article2'\n"
         "Be thorough and include ALL articles."),
        expected_output=
        f"A complete numbered list of all articles from {journal_name}, "
        "with their exact titles and URLs.",
        agent=article_finder_agent)

    # Execute article finding
    finder_crew = Crew(agents=[article_finder_agent],
                       tasks=[find_articles_task],
                       process=Process.sequential,
                       verbose=True)

    print(f"\n🔍 Finding articles for {journal_name}...")
    articles_result = finder_crew.kickoff()
    print(f"\n✅ Found articles from {journal_name}")
    print(f"Result: {articles_result}\n")

    # STEP 2: Parse the article list (you may need to adjust parsing based on actual output format)
    # This is a simplified parser - you might need to make it more robust
    article_list = []
    result_text = str(articles_result)

    # Try to extract article information from the result
    # You may need to adjust this parsing logic based on the actual output format
    lines = result_text.split('\n')
    for line in lines:
        if 'URL:' in line or 'url:' in line.lower():
            article_list.append(line.strip())

    print(f"\n📋 Extracted {len(article_list)} articles to process\n")

    # STEP 3: Process each article sequentially
    processed_articles = []

    for idx, article_info in enumerate(article_list, 1):
        print(f"\n{'─'*60}")
        print(f"Processing Article {idx}/{len(article_list)}")
        print(f"{'─'*60}\n")

        process_article_task = Task(
            description=
            (f"Process the following article from '{journal_name}':\n"
             f"{article_info}\n\n"
             "Perform these steps IN ORDER:\n"
             "1. Scrape the article webpage to extract the full plain text content (body only, no HTML/ads/navigation).\n"
             "2. Generate a concise summary (2-3 sentences) capturing the main points.\n"
             f"3. Determine the article category from: {article_categories}\n"
             f"4. Determine the music style from: {music_styles}\n"
             "5. Extract: title, URL, publication date\n"
             "6. Create a URL-friendly slug from the title\n"
             "7. Use the Save Article Tool with:\n"
             f"   - journal_name: '{journal_name}'\n"
             "   - slug: (generated slug)\n"
             "   - text_content: (scraped plain text)\n"
             "   - metadata: {{'url': ..., 'title': ..., 'date': ..., 'summary': ..., 'category': ..., 'style': ..., 'slug': ...}}\n"
             ),
            expected_output=
            f"Confirmation that the article has been scraped, processed, and saved with all metadata.",
            agent=article_processor_agent)

        processor_crew = Crew(agents=[article_processor_agent],
                              tasks=[process_article_task],
                              process=Process.sequential,
                              verbose=True)

        try:
            result = processor_crew.kickoff()
            processed_articles.append({
                'article_info': article_info,
                'status': 'success',
                'result': str(result)
            })
            print(f"\n✅ Successfully processed article {idx}")
        except Exception as e:
            print(f"\n❌ Error processing article {idx}: {e}")
            processed_articles.append({
                'article_info': article_info,
                'status': 'error',
                'error': str(e)
            })

    return {
        'journal_name':
        journal_name,
        'articles_found':
        len(article_list),
        'articles_processed':
        len([a for a in processed_articles if a['status'] == 'success']),
        'articles_failed':
        len([a for a in processed_articles if a['status'] == 'error']),
        'details':
        processed_articles
    }


if __name__ == "__main__":
    print("🚀 Starting Journal Processing Pipeline...")
    print(f"Processing {len(journals)} journals\n")

    all_results = []

    # Loop over each journal sequentially
    for journal_name, journal_url in journals.items():
        try:
            result = process_journal(journal_name, journal_url)
            all_results.append(result)
        except Exception as e:
            print(f"\n❌ Fatal error processing {journal_name}: {e}")
            all_results.append({
                'journal_name': journal_name,
                'status': 'fatal_error',
                'error': str(e)
            })

    # Print final summary
    print("\n" + "=" * 60)
    print("✅ ALL JOURNALS PROCESSED")
    print("=" * 60)

    for result in all_results:
        if 'articles_found' in result:
            print(f"\n{result['journal_name']}:")
            print(f"  - Articles found: {result['articles_found']}")
            print(
                f"  - Successfully processed: {result['articles_processed']}")
            print(f"  - Failed: {result['articles_failed']}")
        else:
            print(f"\n{result['journal_name']}: FATAL ERROR")

    # Save summary report
    with open(
            f'processing_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            'w') as f:
        json.dump(all_results, f, indent=4)

    print("\n📊 Detailed report saved to processing_report_*.json")
