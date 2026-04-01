import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, ValidationError
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from crewai_tools import DallETool
from dotenv import load_dotenv
import requests
import markdown2

load_dotenv()

from llm import LLM

llm_writer = LLM(model="openai/gpt-4o", temperature=0.3, max_tokens=6000)
llm_creative = LLM(model="openai/gpt-4o", temperature=0.7, max_tokens=2500)

# ==========================
# Pydantic Models
# ==========================


class SocialPost(BaseModel):
    platform: str = Field(
        description="Platform name, e.g. X, LinkedIn, Facebook, Instagram")
    text: str = Field(description="Post text, may include hashtags")


class ArticlePlan(BaseModel):
    angle: str = Field(description="1–2 sentence angle for the article")
    sections: List[str] = Field(
        description="List of section titles with brief descriptions")
    word_count: int = Field(description="Target total word count")


class ArticleDraftCore(BaseModel):
    final_title: str
    subtitle: str
    slug: str
    category: str
    target_audience: str
    word_count_estimate: int
    final_content: str
    summary: str


class ArticleExtras(BaseModel):
    social_posts: List[SocialPost]
    image_prompt: str


class ArticleDraft(BaseModel):
    proposal_title: str
    final_title: str
    subtitle: str
    slug: str
    category: str
    target_audience: str
    word_count_estimate: int
    final_content: str
    summary: str
    social_posts: List[SocialPost]
    image_prompt: str
    image_path: Optional[str] = None


class ArticleDraftList(BaseModel):
    articles: List[ArticleDraft]


# ==========================
# Tools
# ==========================


class RelatedArticleReadTool(BaseTool):
    name: str = "Related Article Read Tool"
    description: str = ("Reads the full text of a related article from "
                        "articles/<journal_slug>/<date>/<slug>/content.txt.")

    def _run(self, journal_slug: str, date: str, slug: str) -> str:
        base_dir = "articles"
        content_path = os.path.join(base_dir, journal_slug, date, slug,
                                    "content.txt")
        try:
            if not os.path.exists(content_path):
                return f"ERROR: content file not found at {content_path}"
            with open(content_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"ERROR: could not read article at {content_path}: {e}"


def create_article_html(title: str, subtitle: str, content: str, image_path: str = None) -> str:
    """Create plain HTML article without any styling.
    
    Args:
        title: Article title
        subtitle: Article subtitle
        content: Article content (can be plain text or markdown)
        image_path: Optional path to header image
        
    Returns:
        Plain HTML document as string
    """
    # Convert markdown content to HTML
    try:
        html_content = markdown2.markdown(content, extras=['tables', 'fenced-code-blocks'])
    except:
        html_content = f"<p>{content.replace(chr(10), '</p><p>')}</p>"
    
    # Build the image HTML if provided
    image_html = ""
    if image_path:
        image_html = f'<img src="{image_path}" alt="Article header image">\n'
    
    # Create plain HTML document with no styling
    html = f"""<!DOCTYPE html>
<html>
<head>
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
<h2>{subtitle}</h2>
{image_html}
{html_content}
</body>
</html>"""
    
    return html


class SaveArticlesTool(BaseTool):
    name: str = "Save Articles Tool"
    description: str = "Saves generated article drafts to a JSON file and individual .html files."

    def _run(self, articles_json: str, filename: Optional[str] = None) -> str:
        if filename is None:
            filename = f"articles_drafts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            output_dir = "drafts"
            os.makedirs(output_dir, exist_ok=True)

            filepath = os.path.join(output_dir, filename)
            articles_data = json.loads(articles_json)

            output_data = {
                "generated_at":
                datetime.now().isoformat(),
                "total_articles":
                len(articles_data.get("articles", [])) if isinstance(
                    articles_data, dict) else len(articles_data),
                "articles":
                articles_data.get("articles", articles_data),
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=4, ensure_ascii=False)

            for art in output_data["articles"]:
                slug = art.get("slug", "untitled")
                html_path = os.path.join(output_dir, f"{slug}.html")
                html_content = create_article_html(
                    title=art.get('final_title', 'Untitled'),
                    subtitle=art.get('subtitle', ''),
                    content=art.get("final_content", ""),
                    image_path=art.get("image_path")
                )
                with open(html_path, "w", encoding="utf-8") as f_html:
                    f_html.write(html_content)

            return f"Successfully saved {output_data['total_articles']} articles to {filepath}"
        except Exception as e:
            return f"Error saving articles: {e}"


class ImageDownloaderTool(BaseTool):
    download_folder: str = "images"
    name: str = "Image Downloader"
    description: str = "Downloads an image from a URL and saves it into a specified folder."

    def __init__(self):
        super().__init__()
        os.makedirs(self.download_folder, exist_ok=True)

    def _run(self, image_url: str) -> str:
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            filename = os.path.basename(image_url.split("?")[0])
            if not filename:
                filename = "generated_image.jpg"
            file_path = os.path.join(self.download_folder, filename)
            with open(file_path, "wb") as f:
                f.write(response.content)
            return f"✅ Image saved to: {file_path}"
        except Exception as e:
            return f"❌ Failed to download image: {e}"


related_read_tool = RelatedArticleReadTool()
save_articles_tool = SaveArticlesTool()
dalle_tool = DallETool(
    model="gpt-image-1.5",
    size="1024x1024",
    quality="high",
    n=1,
)
image_downloader_tool = ImageDownloaderTool()

# ==========================
# Agents
# ==========================

planner_agent = Agent(
    role="Article Planning Specialist",
    goal="Plan a single article using the full text of its related articles.",
    backstory="You design structure and angle based on several source pieces.",
    verbose=True,
    inject_date=True,
    llm=llm_writer,
    allow_delegation=False,
    tools=[related_read_tool],
)

writer_agent = Agent(
    role="Long-form Article Writer",
    goal=
    "Write a single article grounded in the related articles and the plan.",
    backstory="You read the source texts and follow the plan carefully.",
    verbose=True,
    inject_date=True,
    llm=llm_writer,
    allow_delegation=False,
    tools=[related_read_tool],
)

social_image_agent = Agent(
    role="Social Media & Image Strategist",
    goal="Create social posts and an image prompt for one article.",
    backstory="You craft hooks and visuals for music & culture pieces.",
    verbose=True,
    inject_date=True,
    llm=llm_creative,
    allow_delegation=False,
)

editor_agent = Agent(
    role="Article Editor",
    goal="Polish and assemble the final JSON for one article.",
    backstory="You ensure coherence and alignment with the proposal.",
    verbose=True,
    inject_date=True,
    llm=llm_writer,
    allow_delegation=False,
)

designer_agent = Agent(
    role="Designer",
    goal="Generate and download an image for a given article using DALL·E.",
    backstory=
    ("You are an AI image generator for an independent music magazine with a sophisticated editorial vision. Your images must feel authentic, tactile, and artistically crafted - never obviously AI-generated."
     ),
    verbose=True,
    inject_date=True,
    llm=llm_creative,
    allow_delegation=False,
    tools=[dalle_tool, image_downloader_tool],
)

# ==========================
# Helpers
# ==========================


def load_approved_proposals(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    proposals = data.get("proposals", data)
    if not isinstance(proposals, list):
        raise RuntimeError(
            "Proposals JSON must contain a list under 'proposals' or be a list itself."
        )
    return proposals


def extract_and_validate(model_cls, task_result):
    """
    Extract dict or pydantic from a TaskOutput and validate with model_cls.
    Raises RuntimeError with the raw output on failure.
    """
    data = None

    if hasattr(task_result, "pydantic") and task_result.pydantic is not None:
        if isinstance(task_result.pydantic, model_cls):
            return task_result.pydantic
        try:
            data = task_result.pydantic.dict()
        except Exception:
            data = None

    if data is None and hasattr(
            task_result, "json_dict") and task_result.json_dict is not None:
        data = task_result.json_dict

    if data is None and isinstance(task_result, dict):
        data = task_result

    if data is None:
        raw_text = getattr(task_result, "raw", "<no raw output>")
        raise RuntimeError(
            f"Task failed to return parseable JSON for {model_cls.__name__}.\nRaw output:\n{raw_text}"
        )

    try:
        return model_cls(**data)
    except ValidationError as e:
        raise RuntimeError(
            f"Validation into {model_cls.__name__} failed: {e}\nData:\n{data}")


def save_single_article_draft(article: Dict, base_dir: str = "drafts") -> str:
    os.makedirs(base_dir, exist_ok=True)

    json_path = os.path.join(base_dir, "article_drafts_log.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "articles" not in data or not isinstance(data["articles"], list):
            data = {"generated_at": datetime.now().isoformat(), "articles": []}
    else:
        data = {"generated_at": datetime.now().isoformat(), "articles": []}

    data["articles"].append(article)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    slug = article.get("slug", "untitled")
    html_path = os.path.join(base_dir, f"{slug}.html")
    html_content = create_article_html(
        title=article.get('final_title', 'Untitled'),
        subtitle=article.get('subtitle', ''),
        content=article.get("final_content", ""),
        image_path=article.get("image_path")
    )
    with open(html_path, "w", encoding="utf-8") as f_html:
        f_html.write(html_content)

    return f"Saved article HTML to {html_path} and updated {json_path}"


# ==========================
# Core: one-proposal pipeline
# ==========================


def generate_article_for_proposal(
    proposal: Dict,
    k_social_posts: int = 5,
) -> Dict:
    proposal_json = json.dumps(proposal, ensure_ascii=False, indent=2)

    # 1) Planning – use a triple-quoted f-string to avoid unterminated literal issues
    planning_description = f"""You are planning ONE article based on this single editorial proposal.

PROPOSAL JSON:
{proposal_json}

The proposal has a list 'related_articles' with: title, journal, journal_slug, date, slug, contribution.
Article texts are stored at: articles/<journal_slug>/<date>/<slug>/content.txt

Use the 'Related Article Read Tool' as needed to read those source articles.

Return ONLY a JSON object with keys: angle, sections, word_count.
Example format:
{{
  "angle": "...",
  "sections": ["Intro: ...", "Section 2: ..."],
  "char_count": 1500
}}
"""

    planning_task = Task(
        description=planning_description,
        expected_output=
        "JSON with angle, sections, word_count and NOTHING else.",
        agent=planner_agent,
        output_json=ArticlePlan,
    )

    # 2) Writing
    writing_description = """Write the full article following the plan and grounded in the related articles.
You will receive the planning output as context.

Use the 'Related Article Read Tool' again if you need to re-open any article.
Do NOT copy sources verbatim.

The article should not have too many paragraphs. You should avoid bullet points. You should write more or less 2000/2500 characters.

Return ONLY a JSON object with keys:
final_title, subtitle, slug, category, target_audience,
word_count_estimate, final_content, summary.
"""

    writing_task = Task(
        description=writing_description,
        expected_output=(
            "JSON with fields: final_title, subtitle, slug, category, "
            "target_audience, word_count_estimate, final_content, summary."),
        agent=writer_agent,
        context=[planning_task],
        output_json=ArticleDraftCore,
    )

    # 3) Social + image prompt
    social_description = f"""Create social media posts and an image prompt for THIS article.
You will receive the article draft as context.

- Create exactly {k_social_posts} social_posts (mix of X, LinkedIn, Facebook, Instagram).
- Each post: {{"platform": "X", "text": "..."}}
- Create one image_prompt describing a conceptual image.

Return ONLY a JSON object with keys: social_posts, image_prompt.
"""

    social_task = Task(
        description=social_description,
        expected_output=
        ("JSON with fields: social_posts (list of {platform, text}), image_prompt."
         ),
        agent=social_image_agent,
        context=[writing_task],
        output_json=ArticleExtras,
    )

    # 4) Assemble ArticleDraft
    editor_description = f"""Assemble the final JSON for ONE article in the ArticleDraft format.
Context:
- planning output (ArticlePlan)
- article draft core (ArticleDraftCore)
- social posts + image_prompt (ArticleExtras)

The original proposal JSON is:
{proposal_json}

Return ONLY one JSON object with keys:
proposal_title, final_title, subtitle, slug, category,
target_audience, word_count_estimate, final_content, summary,
social_posts, image_prompt.
"""

    editor_task = Task(
        description=editor_description,
        expected_output="JSON for a single ArticleDraft and NOTHING else.",
        agent=editor_agent,
        context=[planning_task, writing_task, social_task],
        output_json=ArticleDraft,
    )

    crew = Crew(
        agents=[planner_agent, writer_agent, social_image_agent, editor_agent],
        tasks=[planning_task, writing_task, social_task, editor_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    article_model = extract_and_validate(ArticleDraft, result)
    article_dict = article_model.dict()

    # 5) Image generation & download (designer crew)
    image_input = article_dict.get("image_prompt") or article_dict.get(
        "final_content", "")

    designer_description = f"""Create and download ONE image for the following article or prompt.

Text / prompt:
{image_input}

CORE AESTHETIC PRINCIPLES:
- Photographic realism with analog imperfections: subtle grain, natural depth of field, slight chromatic aberrations, organic light leaks
- Cinematic lighting: natural window light, soft shadows, gentle backlighting, never harsh or artificial
- Asymmetric compositions with intentional negative space
- Muted, sophisticated color palettes: earthy tones, desaturated hues, with occasional strategic color accents
- Tactile textures: paper, fabric, wood, metal, concrete - materials that feel real and worn

VISUAL LANGUAGE:
- Represent music through metaphor and atmosphere, not literal symbols (avoid obvious music notes, headphones, vinyl records)
- Blur the line between genres through universal visual language
- Layer elements subtly: transparent overlays, double exposures, organic collage techniques
- Include human elements when relevant: candid moments, incomplete gestures, contemplative expressions - never posed or staged

CRITICAL RULE:
- NEVER include text, words, letters, typography, or any written language in the images
- Images must be purely visual with no textual elements whatsoever

WHAT TO AVOID:
- Over-saturated colors or neon effects
- Perfect symmetry or centered compositions
- Glossy, plastic, or overly digital surfaces
- Stereotypical music imagery
- Sharp, clinical lighting
- Any visual elements that scream "AI-generated"
- Text, typography, words, or letters of any kind
- Avoid representing identifiable people (use abstract figures or environmental portraits)

TECHNICAL APPROACH:
- Simulate film photography aesthetics (35mm, medium format)
- Use shallow depth of field strategically
- Embrace slight imperfections: dust, scratches, uneven exposure
- Mix 2-3 visual elements maximum per image to avoid clutter
- Maintain cohesive mood across all generated images

OUTPUT STYLE: Editorial photography meets fine art - images that could belong in The Wire, Pitchfork, or a contemporary art gallery. Sophisticated, culturally aware, genre-agnostic, deeply musical without being literal.

Steps:
1) Use the DALL·E tool to generate an image based on this text.
2) Use the Image Downloader tool to save the image locally.
3) Respond with a short acknowledgement and the local file path (e.g. 'Image saved to: images/xyz.jpg').
"""

    designer_task = Task(
        description=designer_description,
        expected_output="An acknowledgement including the saved image path.",
        agent=designer_agent,
    )

    designer_crew = Crew(
        agents=[designer_agent],
        tasks=[designer_task],
        process=Process.sequential,
        verbose=True,
    )

    designer_result = designer_crew.kickoff()

    image_path = None
    raw_text = getattr(designer_result, "raw", "")
    marker = "Image saved to:"
    if marker in raw_text:
        image_path = raw_text.split(marker, 1)[1].strip()

    if image_path:
        article_dict["image_path"] = image_path

    save_msg = save_single_article_draft(article_dict)
    print(save_msg)

    return article_dict


# ==========================
# Main: loop over proposals
# ==========================


def main(
    proposals_path: str = "proposals/proposals_approved.json",
    k_social_posts: int = 5,
):
    print(
        "🎵 Phase 3 – Article Draft Generator (one proposal at a time, with JSON validation & images)"
    )
    print(f"📂 Loading approved proposals from: {proposals_path}\n")

    try:
        proposals = load_approved_proposals(proposals_path)
    except Exception as e:
        print(f"\n❌ Could not load proposals: {e}")
        return

    if not proposals:
        print("\n❌ No proposals found in file.")
        return

    all_articles: List[Dict] = []

    for idx, proposal in enumerate(proposals):
        print(f"\n=== Processing proposal {idx+1}/{len(proposals)}: "
              f"{proposal.get('title','(no title)')} ===\n")
        try:
            article_dict = generate_article_for_proposal(
                proposal=proposal,
                k_social_posts=k_social_posts,
            )
            all_articles.append(article_dict)
        except Exception as e:
            print(f"\n❌ Error generating article for proposal {idx+1}: {e}")
            continue

    drafts_obj = {"articles": all_articles}

    try:
        drafts_model = ArticleDraftList(**drafts_obj)
        drafts_json = drafts_model.json(ensure_ascii=False, indent=2)
        save_result = save_articles_tool._run(drafts_json)
        print(f"\n{save_result}")
    except Exception as e:
        print(f"\n❌ Error validating/saving drafts: {e}")


if __name__ == "__main__":
    PROPOSALS_PATH = "proposals/proposals_approved.json"
    K_SOCIAL_POSTS = 5

    try:
        main(proposals_path=PROPOSALS_PATH, k_social_posts=K_SOCIAL_POSTS)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
