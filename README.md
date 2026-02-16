# CLEF Article Wizard

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python main.py
   ```

## Workflow
1. **Settings**: configure your API keys (OpenAI, Serper, etc.) and prompts.
2. **Phase 1**: Select journals and scrape articles. They will be saved locally.
3. **Phase 2**: Generate editorial proposals based on scraped articles from the last N days. Review and approve proposals.
4. **Phase 3**: Select an approved proposal, choose a language, and generate the final article with images.
5. **Extras**: Upload an existing text file to generate an image for it.

## Database
A `clef.db` SQLite database is created to track scraped items and proposals.
Generated articles are saved in `generated_articles/`.
Scraped articles are saved in `articles/`.
# clef
