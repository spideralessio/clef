import os
import json
import re
import requests
from typing import Optional, Type, Any, List, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from clef_app.database import DatabaseManager

# --- Download Tool ---
try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

class FixedScrapeWebsiteToolSchema(BaseModel):
    """Input for ScrapeWebsiteTool."""

class ScrapeWebsiteToolSchema(FixedScrapeWebsiteToolSchema):
    """Input for ScrapeWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website url to read the file")

class DownloadPageTool(BaseTool):
    name: str = "Download website HTML"
    description: str = "A tool that can be used to read a website HTML."
    args_schema: Type[BaseModel] = ScrapeWebsiteToolSchema
    website_url: Optional[str] = None
    headers: Optional[dict] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def _run(self, **kwargs: Any) -> Any:
        website_url = kwargs.get("website_url", self.website_url)
        if not website_url:
            return "Error: No URL provided"
            
        try:
            page = requests.get(
                website_url,
                timeout=15,
                headers=self.headers
            )
            
            if BEAUTIFULSOUP_AVAILABLE:
                soup = BeautifulSoup(page.text, 'html.parser')
                
                # Remove script, style, meta, noscript, etc.
                for element in soup(["script", "style", "meta", "noscript", "header", "footer", "iframe", "svg", "nav"]):
                    element.decompose()
                    
                # Get text
                text = soup.get_text(separator=' ', strip=True)
                
                # Clean up whitespace
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Truncate if excessively long (e.g. > 15,000 words approx 20k tokens)
                # Let's take first 50000 chars to be safe (approx 12k tokens)
                # if len(text) > 50000:
                #     text = text[:50000] + "... [TRUNCATED]"
                    
                return text
                
            return page.text
        except Exception as e:
            return f"Error downloading page: {e}"

# --- Article Saving Tool ---

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text

class ArticleMetadataSchema(BaseModel):
    title: str = Field(..., description="Title of the article")
    url: str = Field(..., description="URL of the article")
    date: str = Field(..., description="Publication date")
    summary: str = Field(..., description="Brief summary")
    category: str = Field(..., description="Article category")
    style: str = Field(..., description="Music style or genre")
    slug: Optional[str] = Field(None, description="Slug if available")

class SaveArticleSchema(BaseModel):
    journal_name: str = Field(..., description="Name of the source journal")
    article_date: str = Field(..., description="Publication date in YYYY-MM-DD")
    slug: str = Field(..., description="URL-friendly identifier")
    text_content: str = Field(..., description="Full text content of the article")
    metadata: ArticleMetadataSchema = Field(..., description="Structured metadata for the article")

class SaveArticleTool(BaseTool):
    name: str = "Save Article Tool"
    description: str = "Saves an article's plain text content and metadata to the local filesystem and database."
    args_schema: Type[BaseModel] = SaveArticleSchema

    def _run(self, journal_name: str, article_date: str, slug: str,
             text_content: str, metadata: dict | ArticleMetadataSchema) -> str:
        
        # Ensure metadata is a dict
        if hasattr(metadata, 'dict'):
            metadata = metadata.dict()
        elif hasattr(metadata, 'model_dump'):
            metadata = metadata.model_dump()
        
        base_dir = 'articles'
        try:
            journal_slug = slugify(journal_name)
            if not slug or slug == "None":
                 slug = slugify(metadata.get('title', 'untitled'))

            article_path = os.path.join(base_dir, journal_slug, article_date, slug)
            os.makedirs(article_path, exist_ok=True)

            # Save plain text
            content_file = os.path.join(article_path, 'content.txt')
            with open(content_file, 'w', encoding='utf-8') as f:
                f.write(text_content)

            # Save metadata
            with open(os.path.join(article_path, 'metadata.json'), 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=4)

            # Update DB
            db = DatabaseManager()
            db.add_scraped_article(
                journal=journal_name,
                title=metadata.get('title', 'Unknown'),
                url=metadata.get('url', ''),
                date=article_date,
                slug=slug,
                path=article_path
            )

            return f"Successfully saved article '{slug}'."
        except Exception as e:
            return f"Error saving article '{slug}': {e}"

class LoadArticlesTool(BaseTool):
    name: str = "Load Articles Tool"
    description: str = "Loads all saved articles from the last N days with metadata and content."

    def _run(self, days: int = 7) -> str:
        db = DatabaseManager()
        articles = db.get_scraped_articles(days=days)
        
        result_list = []
        for art in articles:
            # Read content
            path = art['path']
            content_path = os.path.join(path, 'content.txt')
            content = ""
            if os.path.exists(content_path):
                try:
                    with open(content_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except:
                    content = "[Error reading content]"
            
            # Truncate content to avoid token limit, just get first 2000 chars
            result_list.append({
                "title": art['title'],
                "journal": art['journal'],
                "date": art['date'],
                "slug": art['slug'],
                "content": content[:2000] 
            })
            
        return json.dumps(result_list, indent=2)

class VerifyArticleItem(BaseModel):
    journal: str = Field(..., description="Journal name")
    date: str = Field(..., description="Article date")
    slug: str = Field(..., description="Article slug")
    journal_slug: Optional[str] = Field(None, description="Journal slug if known")

class VerifyArticlesSchema(BaseModel):
    articles_to_verify: List[VerifyArticleItem] = Field(..., description="List of articles to verify")

class VerifyArticlesTool(BaseTool):
    name: str = "Verify Articles Tool"
    description: str = "Verifies that articles referenced in a proposal actually exist in the filesystem."
    args_schema: Type[BaseModel] = VerifyArticlesSchema

    def _run(self, articles_to_verify: list | List[Dict[str, Any]]) -> str:
        """Verify articles exist. Input is a list of dicts with 'journal', 'date', 'slug'."""
        base_dir = 'articles'
        results = []
        
        # If input is string (from LLM), try parse
        if isinstance(articles_to_verify, str):
            try:
                articles_to_verify = json.loads(articles_to_verify)
            except:
                return "Error: Input must be a JSON list of article objects."
        
        # If it came as objects (via schema), convert to dict
        if articles_to_verify and hasattr(articles_to_verify[0], 'dict'):
             articles_to_verify = [a.dict() for a in articles_to_verify]
        elif articles_to_verify and hasattr(articles_to_verify[0], 'model_dump'):
             articles_to_verify = [a.model_dump() for a in articles_to_verify]

        for article in articles_to_verify:
            # Handle both formats: 'journal_slug' or just slugify 'journal'
            j_slug = article.get('journal_slug')
            if not j_slug:
                j_slug = slugify(article.get('journal', ''))
                
            date = article.get('date', '')
            slug = article.get('slug', '')

            article_path = os.path.join(base_dir, j_slug, date, slug, 'metadata.json')
            exists = os.path.exists(article_path)
            results.append({
                'slug': slug,
                'exists': exists
            })

        return json.dumps({'results': results}, indent=2)

class RelatedArticleReadTool(BaseTool):
    name: str = "Related Article Read Tool"
    description: str = "Reads the full text of a related article given its path or identifiers."

    def _run(self, journal_slug: str, date: str, slug: str) -> str:
        # If journal_slug looks like a full name (has spaces or capitals), slugify it
        if ' ' in journal_slug or any(c.isupper() for c in journal_slug):
            journal_slug = slugify(journal_slug)
            
        base_dir = "articles"
        # 1. Try constructed path
        content_path = os.path.join(base_dir, journal_slug, date, slug, "content.txt")
        
        if os.path.exists(content_path):
             try:
                with open(content_path, "r", encoding="utf-8") as f:
                    return f.read()
             except Exception as e:
                return f"Error reading article: {e}"
        
        # 2. Smart Recovery: Look up by slug in DB
        # The user might have passed a hallucinated date or journal, but the slug is usually correct.
        try:
             db = DatabaseManager()
             conn = db.get_connection()
             conn.row_factory = None # We just want tuples or dicts
             # Search for strict slug match
             cursor = conn.execute("SELECT path FROM scraped_articles WHERE slug = ?", (slug,))
             row = cursor.fetchone()
             conn.close()
             
             if row:
                 found_path = row[0]
                 found_file = os.path.join(found_path, "content.txt")
                 if os.path.exists(found_file):
                     with open(found_file, "r", encoding="utf-8") as f:
                         return f"Recovered via DB: " + f.read()
                 else:
                     return f"File found in DB but missing on disk at: {found_file}"
        except Exception as db_err:
             print(f"Smart recovery failed: {db_err}")

        # 3. Fallback: Search filesystem for slug if DB fails or empty
        # This is expensive but useful if DB is out of sync
        for root, dirs, files in os.walk(base_dir):
            if slug in root.split(os.sep): # If slug is a folder name in path
                 if "content.txt" in files:
                      try:
                          with open(os.path.join(root, "content.txt"), "r", encoding="utf-8") as f:
                               return f"Recovered via FS search: " + f.read()
                      except:
                          pass

        return f"File not found: {content_path} (and smart recovery failed)"

class ImageDownloaderSchema(BaseModel):
    image_url: str = Field(..., description="The URL of the image to download. It must be a valid http or https URL.")

class ImageDownloaderTool(BaseTool):
    name: str = "Image Downloader"
    description: str = "Downloads an image from a URL and saves it into a specified folder."
    args_schema: Type[BaseModel] = ImageDownloaderSchema
    download_folder: str = "images"

    def _run(self, image_url: str) -> str:
        import json
        import re
        import os
        import requests
        from datetime import datetime

        # Debug logging - Save input
        try:
            os.makedirs(self.download_folder, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f"debug_dalle_{timestamp}.txt"
            debug_path = os.path.join(self.download_folder, debug_filename)
        
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(f"Raw Input: {image_url}\n")
        except:
            pass # Failsafe

        url_to_download = image_url
        
        # 1. Try to clean if JSON
        try:
             # Check if it looks like JSON structure
             if isinstance(image_url, str) and (image_url.strip().startswith('{') or image_url.strip().startswith('[')):
                  data = json.loads(image_url)
                  if isinstance(data, dict):
                       if 'url' in data: url_to_download = data['url']
                       elif 'image_url' in data: url_to_download = data['image_url']
                  elif isinstance(data, list) and len(data) > 0:
                       # Heuristic: first item might be url or dict with url
                       if isinstance(data[0], str): url_to_download = data[0]
                       elif isinstance(data[0], dict): url_to_download = data[0].get('url', url_to_download)
                  
                  with open(debug_path, "a", encoding="utf-8") as f:
                      f.write(f"Parsed JSON, effective URL: {url_to_download}\n")
        except Exception as e:
             with open(debug_path, "a", encoding="utf-8") as f:
                  f.write(f"JSON Parsing Error: {e}\n")

        # 2. Try to clean if Markdown or wrapped text
        # If it doesn't start with http, or has spaces
        if not url_to_download.strip().startswith('http') or ' ' in url_to_download.strip():
             match = re.search(r'(https?://[^\s\)\"\'\]]+)', url_to_download)
             if match:
                 url_to_download = match.group(1)
                 with open(debug_path, "a", encoding="utf-8") as f:
                      f.write(f"Extracted URL from text: {url_to_download}\n")

        # Handle Local File Path if valid
        if os.path.exists(url_to_download.strip()):
             local_path = url_to_download.strip()
             # Optionally copy it to the download folder or just return success
             return f"Image already available locally at: {local_path}"

        try:
            response = requests.get(url_to_download, timeout=15)
            response.raise_for_status()
            
            # Extract filename or generate one
            filename = os.path.basename(url_to_download.split("?")[0])
            if not filename or len(filename) > 50 or '.' not in filename:
                 filename = f"generated_image_{timestamp}.png"
                 
            file_path = os.path.join(self.download_folder, filename)
            
            # Ensure unique name if exists
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(file_path):
                file_path = os.path.join(self.download_folder, f"{base}_{counter}{ext}")
                counter += 1
                
            with open(file_path, "wb") as f:
                f.write(response.content)
            return f"Image saved to: {file_path}"
        except Exception as e:
            with open(debug_path, "a", encoding="utf-8") as f:
                 f.write(f"Download Error: {e}\n")
            return f"Failed to download image: {e}"

class CustomDallEToolSchema(BaseModel):
    prompt: str = Field(..., description="The description of the image to generate.")

class CustomDallETool(BaseTool):
    name: str = "Generate Image"
    description: str = "Generates an image using OpenAI's DALL-E model. Returns a JSON string with the image URL."
    args_schema: Type[BaseModel] = CustomDallEToolSchema
    model: str = "gpt-image-1.5"
    size: str = "1024x1024"
    quality: str = "high"

    def _run(self, prompt: str) -> str:
        log_path = "unknown_log_path"
        try:
            from openai import OpenAI
            from datetime import datetime
            import json
            import os
            
            # Ensure key is present
            if not os.environ.get("OPENAI_API_KEY"):
                from clef_app.config import ConfigManager
                config = ConfigManager()
                api_keys = config.get("api_keys", {})
                if api_keys.get("openai_api_key"):
                     os.environ["OPENAI_API_KEY"] = api_keys["openai_api_key"]
            
            client = OpenAI() 
            
            response = client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
                quality=self.quality,
                n=1,
            )
            
            # Debug log - Save raw response
            try:
                os.makedirs("images", exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_path = f"images/dalle_raw_{ts}.json"
                with open(log_path, "w") as f:
                    try:
                        f.write(response.model_dump_json(indent=2))
                    except:
                        f.write(str(response))
            except Exception as log_err:
                 print(f"Log error: {log_err}")

            item = response.data[0]
            image_url = getattr(item, 'url', None)
            b64 = getattr(item, 'b64_json', None)
            revised_prompt = getattr(item, 'revised_prompt', None)
            
            # If we get base64 instead of URL, save it immediately to avoid token overflow
            if not image_url and b64:
                 try:
                     import base64 as b64lib
                     image_data = b64lib.b64decode(b64)
                     # Use the timestamp from earlier or generate a new one
                     ts_img = datetime.now().strftime("%Y%m%d_%H%M%S")
                     img_filename = f"generated_{ts_img}.png"
                     img_path = os.path.join(os.getcwd(), "images", img_filename)
                     
                     os.makedirs("images", exist_ok=True)
                     with open(img_path, "wb") as img_f:
                         img_f.write(image_data)
                     
                     # Return the local path as the "url"
                     image_url = img_path
                 except Exception as save_err:
                     return f"Error saving base64 image: {save_err}"
            
            if not image_url:
                 return f"Error: No image URL or Base64 data returned. See {log_path} for raw response."

            result = {
                "image_url": image_url,
                "revised_prompt": revised_prompt,
                "note": "Image was saved locally because the model returned base64 data."
            }
            return json.dumps(result)
            
        except Exception as e:
            return f"Error generating image: {str(e)}"
