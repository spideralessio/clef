import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool

from dotenv import load_dotenv

load_dotenv()

from llm import LLM

llm = LLM(model="openai/gpt-4o", temperature=0.3, max_tokens=5000)
llm_chat = LLM(model="openai/gpt-4o", temperature=0.7,
               max_tokens=3000)  # Higher temp for chat

# --- Pydantic Models for Structured Output ---


class RelatedArticle(BaseModel):
    """Model for a related article reference."""
    title: str = Field(description="Article title")
    journal: str = Field(description="Journal name")
    journal_slug: str = Field(
        description="Journal name in slug format (lowercase with hyphens)")
    date: str = Field(description="Article date in YYYY-MM-DD format")
    slug: str = Field(description="Article slug")
    contribution: str = Field(
        description="How this article contributes to the proposal")


class Proposal(BaseModel):
    """Model for an editorial proposal."""
    title: str = Field(description="Compelling proposal title")
    category: str = Field(
        description=
        "Category from: music, culture, reviews, journeys/itineraries/music-trips, interviews, education"
    )
    theme: str = Field(description="Main theme (1-2 sentences)")
    rationale: str = Field(
        description="Why timely and relevant (2-3 sentences)")
    target_audience: str = Field(description="Target audience description")
    content_type: str = Field(
        description="Type of content (e.g., feature article, interview series)"
    )
    key_elements: List[str] = Field(
        description="List of 3-5 specific elements to include")
    related_articles: List[RelatedArticle] = Field(
        description="2-5 related articles that inspired this proposal")
    synthesis_approach: str = Field(
        description="How multiple articles are combined (2-3 sentences)")
    estimated_scope: str = Field(description="Word count or length estimate")
    priority_level: str = Field(description="High, Medium, or Low")


class ProposalList(BaseModel):
    """Model for a list of proposals."""
    proposals: List[Proposal] = Field(
        description="List of editorial proposals")


class UserFeedback(BaseModel):
    """Model for parsed user feedback."""
    action: str = Field(
        description=
        "Action to take: view_all, view_specific, remove_specific, request_more, approve, cancel, general_feedback"
    )
    proposal_index: Optional[int] = Field(
        default=None, description="Proposal number (1-indexed) if applicable")
    additional_requests: Optional[int] = Field(
        default=None, description="Number of additional proposals requested")
    feedback_text: Optional[str] = Field(
        default=None, description="General feedback or comments from user")


# --- Custom Tools ---


class LoadArticlesTool(BaseTool):
    name: str = "Load Articles Tool"
    description: str = "Loads all saved articles from the last N days from the filesystem with complete metadata."

    def _run(self, days: int = 7) -> str:
        """Load articles and return JSON string."""
        base_dir = 'articles'
        articles = []

        today = datetime.now()
        cutoff_date = today - timedelta(days=days)

        try:
            for root, dirs, files in os.walk(base_dir):
                if 'metadata.json' in files:
                    metadata_path = os.path.join(root, 'metadata.json')
                    content_path = os.path.join(root, 'content.txt')

                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)

                        path_parts = root.split(os.sep)
                        journal_name = path_parts[1] if len(
                            path_parts) > 1 else "Unknown"

                        article_date_str = metadata.get('date', '')
                        try:
                            article_date = datetime.strptime(
                                article_date_str, '%Y-%m-%d')
                            if article_date >= cutoff_date:
                                content = ""
                                if os.path.exists(content_path):
                                    with open(content_path,
                                              'r',
                                              encoding='utf-8') as f:
                                        content = f.read()

                                article_info = {
                                    'path':
                                    root,
                                    'journal':
                                    journal_name,
                                    'title':
                                    metadata.get('title', 'Untitled'),
                                    'url':
                                    metadata.get('url', ''),
                                    'date':
                                    article_date_str,
                                    'slug':
                                    metadata.get('slug', ''),
                                    'category':
                                    metadata.get('category', 'uncategorized'),
                                    'style':
                                    metadata.get('style', 'uncategorized'),
                                    'summary':
                                    metadata.get('summary', ''),
                                    'content_preview':
                                    content[:500] if content else "",
                                    'content_length':
                                    len(content)
                                }
                                articles.append(article_info)
                        except ValueError:
                            continue

                    except json.JSONDecodeError:
                        continue

            articles.sort(key=lambda x: x['date'], reverse=True)

            result = {
                'total_articles': len(articles),
                'date_range': {
                    'from': cutoff_date.strftime('%Y-%m-%d'),
                    'to': today.strftime('%Y-%m-%d')
                },
                'articles': articles
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({'error': str(e)})


class VerifyArticlesTool(BaseTool):
    name: str = "Verify Articles Tool"
    description: str = "Verifies that articles referenced in a proposal actually exist in the filesystem."

    def _run(self, articles_to_verify: List[Dict]) -> str:
        """Verify articles exist."""
        base_dir = 'articles'
        results = []

        for article in articles_to_verify:
            journal_slug = article.get('journal_slug', '')
            date = article.get('date', '')
            slug = article.get('slug', '')

            article_path = os.path.join(base_dir, journal_slug, date, slug,
                                        'metadata.json')

            exists = os.path.exists(article_path)
            results.append({
                'journal': article.get('journal', ''),
                'date': date,
                'slug': slug,
                'exists': exists,
                'path': article_path if exists else None
            })

        return json.dumps(
            {
                'total_verified': len(results),
                'all_valid': all(r['exists'] for r in results),
                'results': results
            },
            indent=2)


class SaveProposalsTool(BaseTool):
    name: str = "Save Proposals Tool"
    description: str = "Saves the approved proposals to a JSON file."

    def _run(self, proposals_json: str, filename: str = None) -> str:
        """Save proposals to file."""
        if filename is None:
            filename = f"proposals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            output_dir = 'proposals'
            os.makedirs(output_dir, exist_ok=True)

            filepath = os.path.join(output_dir, filename)

            proposals_data = json.loads(proposals_json)

            output_data = {
                'generated_at':
                datetime.now().isoformat(),
                'total_proposals':
                len(proposals_data) if isinstance(proposals_data, list) else
                len(proposals_data.get('proposals', [])),
                'proposals':
                proposals_data if isinstance(proposals_data, list) else
                proposals_data.get('proposals', [])
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=4, ensure_ascii=False)

            return f"Successfully saved proposals to {filepath}"
        except Exception as e:
            return f"Error saving proposals: {e}"


# --- Agent Definitions ---

load_tool = LoadArticlesTool()
verify_tool = VerifyArticlesTool()
save_tool = SaveProposalsTool()

aggregator_agent = Agent(
    role="Content Aggregator and Analyst",
    goal=
    "Load and analyze all articles, identifying patterns and article clusters.",
    backstory=
    "You are an expert content analyst who finds connections between articles.",
    verbose=True,
    inject_date=True,
    llm=llm,
    allow_delegation=False,
    tools=[load_tool])

proposal_generator_agent = Agent(
    role="Editorial Proposal Specialist",
    goal=
    "Generate creative editorial proposals with verified article references.",
    backstory=
    "You create detailed proposals with proper citations using article slugs and dates. "
    "You always verify that referenced articles exist.",
    verbose=True,
    inject_date=True,
    llm=llm,
    allow_delegation=False,
    tools=[verify_tool])

# Conversational review agent
review_agent = Agent(
    role="Interactive Proposal Review Assistant",
    goal=
    "Help users review proposals through natural conversation, understanding their feedback and executing actions.",
    backstory=
    "You are a helpful editorial assistant who converses naturally with users about proposals. "
    "You understand user requests like 'show me proposal 2', 'remove the third one', 'I like this', "
    "'generate 3 more', 'approve all', etc. You interpret their intent and take appropriate actions. "
    "You're friendly, clear, and help users make decisions about which proposals to keep.",
    verbose=True,
    inject_date=True,
    llm=llm_chat,
    allow_delegation=False,
    tools=[])

# --- Helper Functions ---


def display_proposal(proposal: Dict, index: int):
    """Display a single proposal."""
    print(f"\n{'='*70}")
    print(f"PROPOSAL #{index + 1}")
    print(f"{'='*70}")
    print(f"\n📌 Title: {proposal.get('title', 'N/A')}")
    print(f"📂 Category: {proposal.get('category', 'N/A')}")
    print(f"🎯 Theme: {proposal.get('theme', 'N/A')}")
    print(f"\n💡 Rationale:\n{proposal.get('rationale', 'N/A')}")
    print(f"\n👥 Target Audience: {proposal.get('target_audience', 'N/A')}")
    print(f"📝 Content Type: {proposal.get('content_type', 'N/A')}")
    print(f"⏱️  Priority: {proposal.get('priority_level', 'N/A')}")
    print(f"📏 Scope: {proposal.get('estimated_scope', 'N/A')}")

    print(f"\n🔑 Key Elements:")
    for i, element in enumerate(proposal.get('key_elements', []), 1):
        print(f"  {i}. {element}")

    print(
        f"\n🔗 Related Articles ({len(proposal.get('related_articles', []))}):")
    for i, article in enumerate(proposal.get('related_articles', []), 1):
        print(
            f"  {i}. [{article.get('journal', 'N/A')}] {article.get('title', 'N/A')}"
        )
        print(
            f"     📅 Date: {article.get('date', 'N/A')} | 🔖 Slug: {article.get('slug', 'N/A')}"
        )
        print(f"     💬 {article.get('contribution', 'N/A')}")

    print(
        f"\n🔄 Synthesis Approach:\n{proposal.get('synthesis_approach', 'N/A')}"
    )
    print(f"\n{'='*70}\n")


def ai_interactive_review(proposals: List[Dict], days: int) -> List[Dict]:
    """
    AI-powered interactive review session.
    The AI agent interprets user requests and manages the conversation.
    """
    print("\n" + "=" * 70)
    print("🤖 AI-POWERED PROPOSAL REVIEW SESSION")
    print("=" * 70)
    print("\nI'm your AI assistant! I'll help you review these proposals.")
    print("You can ask me to:")
    print("  - Show proposals (e.g., 'show all', 'show proposal 2')")
    print(
        "  - Remove proposals (e.g., 'remove proposal 3', 'delete the first one')"
    )
    print("  - Generate more (e.g., 'create 3 more proposals')")
    print("  - Approve (e.g., 'approve these', 'save them', 'looks good')")
    print("  - Cancel (e.g., 'cancel', 'exit', 'never mind')")
    print("\nJust talk naturally - I'll understand!\n")

    current_proposals = proposals.copy()
    conversation_history = []

    while True:
        user_input = input("\n💬 You: ").strip()

        if not user_input:
            continue

        conversation_history.append(f"User: {user_input}")

        # Create a task for the review agent to parse and respond
        parse_task = Task(
            description=
            (f"The user said: '{user_input}'\n\n"
             f"Current state: We have {len(current_proposals)} proposals under review.\n\n"
             f"Conversation history:\n" +
             "\n".join(conversation_history[-5:]) + "\n\n"
             "Analyze what the user wants to do. Determine the action from these options:\n"
             "- 'view_all': User wants to see all proposals\n"
             "- 'view_specific': User wants to see a specific proposal (extract the number)\n"
             "- 'remove_specific': User wants to remove a proposal (extract the number)\n"
             "- 'request_more': User wants more proposals (extract how many)\n"
             "- 'approve': User wants to approve and save all proposals\n"
             "- 'cancel': User wants to cancel/exit\n"
             "- 'general_feedback': User is providing feedback or asking questions\n\n"
             "Respond naturally to the user, acknowledging their request and explaining what you'll do. "
             "If you need clarification, ask for it. Be conversational and helpful."
             ),
            expected_output=
            ("A natural, conversational response to the user that:\n"
             "1. Acknowledges what they asked for\n"
             "2. Explains what action will be taken\n"
             "3. Provides any relevant information or asks for clarification if needed"
             ),
            agent=review_agent,
            output_json=UserFeedback)

        review_crew = Crew(agents=[review_agent],
                           tasks=[parse_task],
                           process=Process.sequential,
                           verbose=False)

        result = review_crew.kickoff()

        # Get the parsed feedback
        try:
            feedback = result.json_dict if hasattr(
                result, 'json_dict') else result.pydantic.dict()
            action = feedback.get('action', 'general_feedback')

            # Get the AI's conversational response
            ai_response = result.raw if hasattr(result, 'raw') else str(result)
            print(f"\n🤖 AI: {ai_response}")

            conversation_history.append(f"AI: {ai_response}")

            # Execute the action
            if action == 'approve':
                if not current_proposals:
                    print("\n⚠️  No proposals to save!")
                    continue
                print(f"\n✅ Approving {len(current_proposals)} proposals...")
                return current_proposals

            elif action == 'cancel':
                print("\n❌ Review canceled. No proposals will be saved.")
                return []

            elif action == 'view_all':
                print(f"\n📋 Showing all {len(current_proposals)} proposals:\n")
                for i, prop in enumerate(current_proposals):
                    print(
                        f"  {i + 1}. {prop.get('title', 'Untitled')} [{prop.get('category', 'N/A')}]"
                    )

            elif action == 'view_specific':
                idx = feedback.get('proposal_index', 0) - 1
                if 0 <= idx < len(current_proposals):
                    display_proposal(current_proposals[idx], idx)
                else:
                    print(
                        f"\n⚠️  Invalid proposal number. Choose between 1 and {len(current_proposals)}"
                    )

            elif action == 'remove_specific':
                idx = feedback.get('proposal_index', 0) - 1
                if 0 <= idx < len(current_proposals):
                    removed = current_proposals.pop(idx)
                    print(f"\n✅ Removed: {removed.get('title', 'Untitled')}")
                    print(f"   Remaining: {len(current_proposals)} proposals")
                else:
                    print(
                        f"\n⚠️  Invalid proposal number. Choose between 1 and {len(current_proposals)}"
                    )

            elif action == 'request_more':
                num = feedback.get('additional_requests', 3)
                print(
                    f"\n🔄 Generating {num} more proposals based on the same data..."
                )

                # Generate more proposals
                new_proposals = generate_more_proposals(days, num)
                if new_proposals:
                    current_proposals.extend(new_proposals)
                    print(
                        f"✅ Added {len(new_proposals)} new proposals. Total: {len(current_proposals)}"
                    )

                    # Show the new ones
                    print("\n📋 New proposals:")
                    for i, prop in enumerate(new_proposals):
                        print(
                            f"  {len(current_proposals) - len(new_proposals) + i + 1}. {prop.get('title', 'Untitled')}"
                        )
                else:
                    print("❌ Could not generate additional proposals.")

            elif action == 'general_feedback':
                # AI already responded, just continue the conversation
                pass

        except Exception as e:
            print(f"\n⚠️  Error processing request: {e}")
            print("Please try rephrasing your request.")


def generate_more_proposals(days: int, num: int) -> List[Dict]:
    """Generate additional proposals."""
    print(f"\n🔄 Generating {num} additional proposals...")

    analyze_task = Task(
        description=
        (f"Use the Load Articles Tool to get articles from the last {days} days. "
         "Identify new angles and themes that haven't been covered yet in previous proposals. "
         "Find different article clusters to create fresh, unique proposals."),
        expected_output=
        "Analysis with new article clusters for generating additional proposals.",
        agent=aggregator_agent)

    generate_task = Task(description=(
        f"Create exactly {num} NEW editorial proposals different from any previous ones.\n\n"
        "Each proposal must follow the Proposal model structure with all required fields:\n"
        "- title, category, theme, rationale, target_audience, content_type\n"
        "- key_elements (list of 3-5 items)\n"
        "- related_articles (list of 2-5 RelatedArticle objects with: title, journal, journal_slug, date, slug, contribution)\n"
        "- synthesis_approach, estimated_scope, priority_level\n\n"
        "Use the Verify Articles Tool to ensure all referenced articles exist.\n"
        "Return as a ProposalList with a 'proposals' field containing the list of Proposal objects."
    ),
                         expected_output=
                         f"{num} new verified proposals in ProposalList format.",
                         agent=proposal_generator_agent,
                         output_json=ProposalList,
                         context=[analyze_task])

    crew = Crew(agents=[aggregator_agent, proposal_generator_agent],
                tasks=[analyze_task, generate_task],
                process=Process.sequential,
                verbose=False)

    result = crew.kickoff()

    try:
        proposals_data = result.json_dict if hasattr(
            result, 'json_dict') else result.pydantic.dict()
        return proposals_data.get('proposals', [])
    except:
        return []


def generate_initial_proposals(days: int, num_proposals: int) -> List[Dict]:
    """Generate initial set of proposals with structured output."""
    print(f"\n🚀 Generating {num_proposals} initial proposals...\n")

    analyze_task = Task(
        description=
        (f"Use the Load Articles Tool to retrieve all articles from the last {days} days.\n"
         "Analyze and identify:\n"
         "1. Common themes and article clusters that can be combined\n"
         "2. Different perspectives from multiple journals\n"
         "3. Categories and styles represented\n"
         "Provide comprehensive analysis for generating proposals."),
        expected_output=
        ("Detailed analysis with article clusters including metadata (journal, date, slug, category) "
         "for each article."),
        agent=aggregator_agent)

    generate_task = Task(
        description=
        (f"Based on the analysis, create exactly {num_proposals} editorial proposals.\n\n"
         "Use the ProposalList Pydantic model structure. Each Proposal must have:\n"
         "- title: str\n"
         "- category: str (one of: music, culture, reviews, journeys/itineraries/music-trips, interviews, education)\n"
         "- theme: str\n"
         "- rationale: str\n"
         "- target_audience: str\n"
         "- content_type: str\n"
         "- key_elements: List[str] (3-5 items)\n"
         "- related_articles: List[RelatedArticle] (2-5 items, each with: title, journal, journal_slug, date, slug, contribution)\n"
         "- synthesis_approach: str\n"
         "- estimated_scope: str\n"
         "- priority_level: str (High/Medium/Low)\n\n"
         "IMPORTANT: Use the Verify Articles Tool to check all article references exist before finalizing.\n"
         "Only include verified articles.\n\n"
         "Return the output as a ProposalList object with a 'proposals' field."
         ),
        expected_output=
        f"ProposalList with {num_proposals} verified Proposal objects.",
        agent=proposal_generator_agent,
        output_json=ProposalList,
        context=[analyze_task])

    crew = Crew(agents=[aggregator_agent, proposal_generator_agent],
                tasks=[analyze_task, generate_task],
                process=Process.sequential,
                verbose=True)

    result = crew.kickoff()

    try:
        # Access structured output
        if hasattr(result, 'json_dict'):
            proposals_data = result.json_dict
        elif hasattr(result, 'pydantic'):
            proposals_data = result.pydantic.dict()
        else:
            proposals_data = result

        proposals = proposals_data.get('proposals', [])
        print(f"\n✅ Successfully generated {len(proposals)} proposals")
        return proposals
    except Exception as e:
        print(f"\n❌ Error parsing proposals: {e}")
        print(f"Result type: {type(result)}")
        if hasattr(result, '__dict__'):
            print(f"Result attributes: {result.__dict__.keys()}")
        return []


# --- Main Function ---


def main(days: int = 7, num_proposals: int = 5):
    """Main function with AI-powered human-in-the-loop."""
    print("🎵 Editorial Proposal Generator with AI Review Assistant")
    print(f"📅 Analyzing articles from last {days} days")
    print(f"📝 Generating {num_proposals} initial proposals\n")

    # Generate initial proposals
    proposals = generate_initial_proposals(days, num_proposals)

    if not proposals:
        print("\n❌ No proposals were generated. Check the logs above.")
        return

    # Display all proposals
    print("\n" + "=" * 70)
    print("GENERATED PROPOSALS")
    print("=" * 70)
    for i, proposal in enumerate(proposals):
        display_proposal(proposal, i)

    # Start AI-powered interactive review
    approved_proposals = ai_interactive_review(proposals, days)

    if approved_proposals:
        # Save approved proposals
        proposals_json = json.dumps(approved_proposals, indent=2)
        result = save_tool._run(proposals_json)
        print(f"\n{result}")
        print(
            f"✅ Successfully saved {len(approved_proposals)} approved proposals!"
        )
    else:
        print("\n❌ No proposals were saved.")


if __name__ == "__main__":
    N_DAYS = 3
    K_PROPOSALS = 5

    try:
        main(days=N_DAYS, num_proposals=K_PROPOSALS)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
