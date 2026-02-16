import json
import logging
from typing import List, Dict
from crewai import Agent, Task, Crew, Process
from clef_app.config import ConfigManager
from clef_app.llm_provider import get_llm
from clef_app.tools import LoadArticlesTool, VerifyArticlesTool
from clef_app.models import ProposalList, Proposal, UserFeedback
from clef_app.database import DatabaseManager

class Phase2Runner:
    def __init__(self):
        self.config = ConfigManager()
        self.llm = get_llm()
        self.db = DatabaseManager()
        self.prompts = self.config.get("prompts", {})
        self.max_rpm = self.config.get("settings", {}).get("max_rpm", 10)
        self.logger = logging.getLogger("clef_app.logic.phase_2")

    def _get_aggregator_agent(self) -> Agent:
        return Agent(
            role="Content Aggregator and Analyst",
            goal="Analyze articles to identify themes, trends, and content gaps.",
            backstory=self.prompts.get("aggregator", "You are an expert analyst..."),
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False,
            tools=[LoadArticlesTool()]
        )

    def _get_proposal_agent(self) -> Agent:
        return Agent(
            role="Editorial Proposal Specialist",
            goal="Analyze articles and generate verified editorial proposals.",
            backstory=self.prompts.get("proposal_generation", 
                "You create detailed proposals with proper citations..."
            ),
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False,
            tools=[VerifyArticlesTool()]
        )

    def _get_feedback_agent(self) -> Agent:
        return Agent(
            role="Feedback Analyst",
            goal="Analyze user feedback on editorial proposals and determine next steps.",
            backstory="You are an expert at understanding editorial direction...",
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False
        )

    def generate_initial_proposals(self, days: int = 7, num_proposals: int = 5) -> List[Proposal]:
        aggregator = self._get_aggregator_agent()
        proposal_maker = self._get_proposal_agent()
        
        # Pre-fetch valid articles metadata to inject into context
        articles = self.db.get_scraped_articles(days=days)
        valid_slugs_text = "AVAILABLE ARTICLES (Use EXACTLY these details):\n"
        for a in articles:
            valid_slugs_text += f"- Title: {a['title']}\n  Journal: {a['journal']}\n  Date: {a['date']}\n  Slug: {a['slug']}\n"
        
        analyze_task = Task(
            description=
            (f"Use the Load Articles Tool to retrieve all articles from the last {days} days.\n"
             "Analyze and identify:\n"
             "1. Common themes and article clusters that can be combined\n"
             "2. Different perspectives from multiple journals\n"
             "3. Categories and styles represented\n\n"
             "CRITICAL: You MUST include a 'Reference List' section at the end of your analysis. "
             "This list must contain the EXACT 'journal', 'date', and 'slug' for every article you analyzed. "
             "The next agent depends on this list to verify files."),
            expected_output="Detailed analysis with article clusters and a complete Reference List of used articles.",
            agent=aggregator
        )

        generate_task = Task(
            description=
            (f"Based on the analysis, create exactly {num_proposals} editorial proposals.\n\n"
             "Use the ProposalList Pydantic model structure. Each Proposal must have:\n"
             "- title, category, theme, rationale, target_audience, content_type\n"
             "- key_elements (list of 3-5 items)\n"
             "- related_articles (list of 2-5 RelatedArticle objects...)\n"
             "- synthesis_approach, estimated_scope, priority_level\n\n"
             "IMPORTANT: You MUST ONLY use articles from the list below. Do NOT invent new articles.\n"
             f"{valid_slugs_text}\n\n"
             "Use the Verify Articles Tool to confirm these articles exist. Pass the EXACT parameters found in the list above.\n"
             "Return the output as a ProposalList object."
             ),
            expected_output=f"{num_proposals} proposals in ProposalList format.",
            agent=proposal_maker,
            output_pydantic=ProposalList,
            context=[analyze_task]
        )
        
        crew = Crew(
            agents=[aggregator, proposal_maker],
            tasks=[analyze_task, generate_task],
            process=Process.sequential,
            verbose=True
        )
        
        result = crew.kickoff()
        
        try:
            if hasattr(result, 'pydantic') and result.pydantic:
                return result.pydantic.proposals
            return []
        except Exception as e:
            self.logger.error(f"Error parsing proposals: {e}")
            return []

    def process_user_feedback(self, feedback_text: str) -> UserFeedback:
        feedback_agent = self._get_feedback_agent()
        
        task = Task(
             description=f"""
             Analyze the following user feedback regarding editorial proposals:
             "{feedback_text}"
             
             Map it to the UserFeedback structure:
             - action: view_all, view_specific, remove_specific, request_more, approve, cancel, general_feedback
             - proposal_index: number if mentioned (1-indexed)
             - additional_requests: number if asking for more
             - feedback_text: The cleaned up feedback query
             """,
             expected_output="Parsed UserFeedback object.",
             agent=feedback_agent,
             output_pydantic=UserFeedback
        )
        
        crew = Crew(agents=[feedback_agent], tasks=[task], verbose=True)
        result = crew.kickoff()
        
        try:
            if hasattr(result, 'pydantic') and result.pydantic:
                return result.pydantic
        except:
            pass
            
        return UserFeedback(action="general_feedback", feedback_text=feedback_text)

    def generate_more_proposals(self, days: int, num: int) -> List[Proposal]:
        aggregator = self._get_aggregator_agent()
        proposal_maker = self._get_proposal_agent()
        
        # Pre-fetch valid articles metadata
        articles = self.db.get_scraped_articles(days=days)
        valid_slugs_text = "AVAILABLE ARTICLES (Use EXACTLY these details):\n"
        for a in articles:
            valid_slugs_text += f"- Title: {a['title']}\n  Journal: {a['journal']}\n  Date: {a['date']}\n  Slug: {a['slug']}\n"

        analyze_task = Task(
            description=
            (f"Use the Load Articles Tool to get articles from the last {days} days. "
             "Identify new angles and themes that haven't been covered yet. "
             "CRITICAL: Include a 'Reference List' of all articles with their exact 'slug', 'date', and 'journal'."),
            expected_output="Analysis for new proposals with Reference List.",
            agent=aggregator
        )

        generate_task = Task(
            description=(
                f"Create exactly {num} NEW editorial proposals different from any previous ones.\n\n"
                "Follow the Proposal model structure (ProposalList output).\n"
                "IMPORTANT: You MUST ONLY use articles from the list below. Do NOT invent new articles.\n"
                f"{valid_slugs_text}\n\n"
                "Use the 'Reference List' from the context to correctly invoke Verify Articles Tool.\n"
                "Ensure slugs and dates are exact matches from the loaded list.\n"
            ),
            expected_output=f"{num} new verified proposals in ProposalList format.",
            agent=proposal_maker,
            output_pydantic=ProposalList,
            context=[analyze_task]
        )

        crew = Crew(
            agents=[aggregator, proposal_maker],
            tasks=[analyze_task, generate_task],
            verbose=True
        )

        result = crew.kickoff()
        
        try:
            if hasattr(result, 'pydantic') and result.pydantic:
                return result.pydantic.proposals
            return []
        except Exception as e:
            print(f"Error parsing additional proposals: {e}")
            return []
            
    def save_proposal(self, proposal: Proposal):
        # Handle Pydantic v1 vs v2
        data = proposal.model_dump() if hasattr(proposal, 'model_dump') else proposal.dict()
        # Pass the raw Pydantic dict. DatabaseManager will handle extraction and JSON dumping.
        self.db.add_proposal(data)
