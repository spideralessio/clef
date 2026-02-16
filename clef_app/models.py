from pydantic import BaseModel, Field
from typing import List, Optional

class RelatedArticle(BaseModel):
    title: str = Field(description="Article title")
    journal: str = Field(description="Journal name")
    date: str = Field(description="Article date")
    slug: str = Field(description="Article slug")
    contribution: str = Field(description="How this article contributes")

class Proposal(BaseModel):
    title: str = Field(description="Compelling proposal title")
    category: str = Field(description="Category")
    theme: str = Field(description="Main theme")
    rationale: str = Field(description="Why timely and relevant")
    target_audience: str = Field(description="Target audience")
    content_type: str = Field(description="Type of content")
    key_elements: List[str] = Field(description="Specific elements to include")
    related_articles: List[RelatedArticle] = Field(description="Related articles")
    synthesis_approach: str = Field(description="How articles are combined")
    estimated_scope: str = Field(description="Word count")
    priority_level: str = Field(description="High, Medium, or Low")

class ProposalList(BaseModel):
    proposals: List[Proposal] = Field(description="List of editorial proposals")

class UserFeedback(BaseModel):
    """Model for parsed user feedback."""
    action: str = Field(
        description="Action to take: view_all, view_specific, remove_specific, request_more, approve, cancel, general_feedback"
    )
    proposal_index: Optional[int] = Field(
        default=None, description="Proposal number (1-indexed) if applicable"
    )
    additional_requests: Optional[int] = Field(
        default=None, description="Number of additional proposals requested"
    )
    feedback_text: Optional[str] = Field(
        default=None, description="General feedback or comments from user"
    )

class SocialPost(BaseModel):
    platform: str
    text: str

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

