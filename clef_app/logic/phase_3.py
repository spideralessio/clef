import os
import json
import logging
from typing import Optional, Dict, List
from crewai import Agent, Task, Crew, Process
from crewai_tools import DallETool
from clef_app.config import ConfigManager
from clef_app.llm_provider import get_llm
from clef_app.models import Proposal, ArticleDraft
from clef_app.tools import RelatedArticleReadTool, ImageDownloaderTool
from clef_app.database import DatabaseManager

class Phase3Runner:
    def __init__(self):
        self.config = ConfigManager()
        self.llm = get_llm() # Standard LLM
        self.llm_creative = get_llm(temperature=0.7)
        self.db = DatabaseManager()
        self.max_rpm = self.config.get("settings", {}).get("max_rpm", 10)
        self.logger = logging.getLogger("clef_app.logic.phase_3")

    def write_article(self, proposal: Proposal, language: str = "italian") -> Optional[ArticleDraft]:
        prompts = self.config.get("prompts", {})
        
        # Tools
        read_tool = RelatedArticleReadTool()
        dalle_tool = DallETool(model="dall-e-3", size="1024x1024", quality="standard", n=1)
        image_dl_tool = ImageDownloaderTool()
        
        # Agents
        planner_agent = Agent(
            role="Article Planning Specialist",
            goal="Plan a single article using the full text of its related articles.",
            backstory=prompts.get("plan_article", "You design structure and angle based on several source pieces."),
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False,
            tools=[read_tool]
        )

        writer_agent = Agent(
            role="Long-form Article Writer",
            goal="Write a single article grounded in the related articles and the plan.",
            backstory=prompts.get("write_article", "You read the source texts and follow the plan carefully."),
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False,
            tools=[read_tool]
        )
        
        social_image_agent = Agent(
            role="Social Media & Image Strategist",
            goal="Create social posts and an image prompt for one article.",
            backstory=prompts.get("marketing_strategy", "You craft hooks and visuals for music & culture pieces."),
            verbose=True,
            llm=self.llm_creative,
            max_rpm=self.max_rpm,
            allow_delegation=False
        )

        editor_agent = Agent(
            role="Article Editor",
            goal="Polish and assemble the final JSON for one article.",
            backstory=prompts.get("edit_article", "You ensure coherence and alignment with the proposal."),
            verbose=True,
            llm=self.llm,
            max_rpm=self.max_rpm,
            allow_delegation=False
        )
        
        designer_agent = Agent(
            role="Designer",
            goal="Generate and download an image for a given article using DALL·E.",
            backstory=prompts.get("design_image", "You are an AI image generator for an independent music magazine..."),
            verbose=True,
            llm=self.llm_creative,
            max_rpm=self.max_rpm,
            allow_delegation=False,
            tools=[dalle_tool, image_dl_tool]
        )

        # Context construction
        related_articles_context = "\n".join([
            f"- Title: {ra.title}\n  Journal: {ra.journal}\n  Slug: {ra.slug}\n  Date: {ra.date}\n  Contribution: {ra.contribution}"
            for ra in proposal.related_articles
        ])

        # Tasks
        task_plan = Task(
            description=f"""
            Plan the article based on:
            Title: {proposal.title}
            Theme: {proposal.theme}
            Rationale: {proposal.rationale}
            Target Audience: {proposal.target_audience}
            
            Related Articles (use RelatedArticleReadTool if needed):
            {related_articles_context}
            
            Output a detailed outline (sections, angle, word count).
            """,
            expected_output="A detailed article plan.",
            agent=planner_agent
        )
        
        task_write = Task(
            description=f"""
            Write the full article using the plan.
            Output Language: {language}
            Capture the tone and style appropriate for the audience.
            """,
            expected_output="Full markdown text of the article.",
            agent=writer_agent,
            context=[task_plan]
        )
        
        task_social = Task(
            description=f"""
            Based on the written article, create:
            1. Two social media posts (e.g. for Instagram/X).
            2. An image generation prompt describing a visual for the header.
            """,
            expected_output="Social posts and image prompt.",
            agent=social_image_agent,
            context=[task_write]
        )
        
        task_edit = Task(
            description=f"""
            Review the article, plan, and social content.
            Output the FINAL result as a structured JSON object matching the ArticleDraft model.
            Must include: final_title, subtitle, slug, category, target_audience, word_count_estimate, final_content (the full text), summary, social_posts, image_prompt.
            """,
            expected_output="Final structured JSON for the article.",
            agent=editor_agent,
            output_pydantic=ArticleDraft,
            context=[task_plan, task_write, task_social]
        )
        
        # Design Task - runs after edit to use the image prompt
        task_design = Task(
            description=f"""
            Using the 'image_prompt' from the Editor's output:
            1. Generate an image using DALL-E.
            2. Download the image using ImageDownloader (it returns the path).
            
            Return the local file path of the downloaded image.
            """,
            expected_output="The file path of the downloaded image.",
            agent=designer_agent,
            context=[task_edit]
        )
        
        crew = Crew(
            agents=[planner_agent, writer_agent, social_image_agent, editor_agent, designer_agent],
            tasks=[task_plan, task_write, task_social, task_edit, task_design],
            verbose=True,
            process=Process.sequential
        )
        
        try:
            result = crew.kickoff()
            
            # Access outputs
            draft = task_edit.output.pydantic
            if not draft:
                # Try simple parsing if pydantic missing (older crewai versions sometimes)
                 # But we assume new version.
                 self.logger.warning("Warning: Pydantic output missing from edit task.")
                 return None

            image_path_res = str(task_design.output.raw)
            
            # Helper to extract path if mixed with text
            if "Image saved to: " in image_path_res:
                draft.image_path = image_path_res.split("Image saved to: ")[-1].strip()
            else:
                 draft.image_path = image_path_res
            
            self.save_draft(draft, proposal.title, language)
            return draft
            
        except Exception as e:
            self.logger.error(f"Error writing article: {e}")
            return None

    def generate_image(self, prompt: str, filename_prefix: str, output_dir: str = "images") -> Optional[str]:
        # Standalone image generation (Extras tab)
        dalle_tool = DallETool(model="dall-e-3", size="1024x1024", quality="standard", n=1)
        image_dl_tool = ImageDownloaderTool(download_folder=output_dir)
        
        agent = Agent(
            role="Designer",
            goal="Generate image.",
            backstory="You generate images.",
            llm=get_llm(temperature=0.7),
            tools=[dalle_tool, image_dl_tool]
        )
        
        task = Task(
            description=f"Generate image for: {prompt}. Download it.",
            expected_output="Path to image.",
            agent=agent
        )
        
        crew = Crew(agents=[agent], tasks=[task], verbose=True)
        return str(crew.kickoff())

    def save_draft(self, draft: ArticleDraft, proposal_title: str, language: str):
         base_dir = "generated_articles"
         slug = draft.slug 
         path = os.path.join(base_dir, slug)
         os.makedirs(path, exist_ok=True)
         
         # MD File
         with open(os.path.join(path, "article.md"), "w", encoding="utf-8") as f:
             f.write(f"# {draft.final_title}\n\n")
             f.write(f"## {draft.subtitle}\n\n")
             if draft.image_path:
                 f.write(f"![Header Image]({draft.image_path})\n\n")
             f.write(f"{draft.final_content}")
             
         # Social Posts
         social_dir = os.path.join(path, "social")
         os.makedirs(social_dir, exist_ok=True)
         
         for i, post in enumerate(draft.social_posts):
             # safe filename
             platform_safe = "".join(x for x in post.platform if x.isalnum())
             if not platform_safe:
                 platform_safe = "platform"
             
             post_filename = f"{i+1}_{platform_safe}.txt"
             post_path = os.path.join(social_dir, post_filename)
             
             with open(post_path, "w", encoding="utf-8") as f:
                 f.write(post.text)

         # JSON Metadata
         with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
             json.dump(draft.dict(), f, indent=4)
             
         self.db.add_generated_article(0, draft.final_title, slug, path, language)
