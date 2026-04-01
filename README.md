# CLEF - Content & Lead Editorial Framework

CLEF is an AI-powered desktop application designed to streamline the editorial process for music journalism (and beyond). It automates the workflow from scouting news to publishing drafts on WordPress.

## Features

*   **Phase 1: Scraper**
    *   Scrape articles from configured source websites (e.g., Rolling Stone).
    *   Intelligent parsing of article dates, including relative dates (e.g., "2 hours ago").
    *   Automatic categorization and summarization using AI.
    *   Saves content locally in a structured folder format.
    
*   **Phase 2: Editorial Proposals**
    *   Analyzes scraped articles from the last N days.
    *   Identifies trends and clusters.
    *   Generates pitched editorial proposals with rationales and angles.
    *   Interactive chat to refine proposals with the AI agent.
    
*   **Phase 3: Writer & Publisher**
    *   Drafts full articles based on approved proposals.
    *   Multilingual support (Italian, English, etc.).
    *   Generates SEO-friendly slugs and social media posts.
    *   **Image Generation**: Creates DALL-E 3 images for the articles.
    *   **WordPress Integration**: Uploads the draft, images, and metadata directly to your WordPress site.

*   **Extras**
    *   Generate images for existing text files.
    
*   **Logging**
    *   Full logging of operations to `logs/` directory for debugging.

## Setup

1.  **Prerequisites**:
    *   Python 3.10+
    *   Valid OpenAI API Key (GPT-4o recommended).
    *   (Optional) WordPress Application Password for publishing.

2.  **Installation**:
    ```bash
    # Create virtual environment
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Run the Application**:
    ```bash
    python main.py
    ```

## Usage Guide

1.  **Settings Tab**:
    *   Enter your OpenAI API key.
    *   Configure WordPress credentials (URL, Username, App Password).
    *   Manage your list of Source URLs.
    *   Customize system prompts if needed.
    *   Click "Save All Settings".

2.  **Phase 1 (Scrape)**:
    *   Select sources to scrape.
    *   Click "Run Scraping".
    *   Monitor the detailed logs in the text area.

3.  **Phase 2 (Proposals)**:
    *   Click "Generate Initial Proposals".
    *   Chat with the AI to refine or request more ideas.
    *   Select a proposal and click "Save Selected to DB" to approve it.

4.  **Phase 3 (Write)**:
    *   Refresh the list of approved proposals.
    *   Select a proposal and choose the target language.
    *   Tick "Upload to WordPress" if desired.
    *   Click "Write Article".
    *   The app will generate text, images, and social posts, then save to disk and upload.

## Project Structure

*   `clef_app/`: Main source code.
    *   `gui/`: Tkinter interface.
    *   `logic/`: Business logic for each phase (CrewAI agents).
*   `articles/`: Raw scraped data warehouse.
*   `generated_articles/`: Final outputs (HTML, JSON, Images).
*   `logs/`: Application execution logs.
*   `clef.db`: SQLite database storing state.
*   `config.json`: User configuration (ignored by git).

## License
[MIT](LICENSE)
