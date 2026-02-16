import requests
import json
import base64
from requests.auth import HTTPBasicAuth
from typing import Dict, Optional, List

class WordPressClient:
    def __init__(self, url: str, username: str, app_password: str):
        self.url = url.rstrip('/')
        self.username = username.strip()
        # WordPress Application Passwords ignore spaces, but standard Basic Auth does not.
        # We strip them to ensure clean transport.
        self.password = app_password.replace(" ", "")
        
        # Determine initial API URL (default standard)
        self.api_url = f"{self.url}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(self.username, self.password)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
        }

    def validate_connection(self) -> bool:
        try:
            # 1. Try Standard API URL
            check_url = f"{self.api_url}/users/me?context=edit" 
            print(f"Testing WP Connection (Standard): {check_url}")
            
            response = requests.get(check_url, auth=self.auth, headers=self.headers)
            
            if response.status_code == 200:
                print("WP Connection Successful (Standard).")
                return True
            
            print(f"Standard path failed ({response.status_code}). Trying fallback to ?rest_route=...")
            
            # 2. Try Fallback API URL (Bypasses potential Header Stripping servers)
            # e.g. /?rest_route=/wp/v2
            fallback_api_url = f"{self.url}/?rest_route=/wp/v2"
            check_url_fallback = f"{fallback_api_url}/users/me"
            
            response_fb = requests.get(check_url_fallback, auth=self.auth, headers=self.headers, params={"context": "edit"})
            
            if response_fb.status_code == 200:
                print("WP Connection Successful (Fallback Route). Switching API URL.")
                self.api_url = fallback_api_url
                return True

            print(f"WP Connection Failed: {response.status_code}")
            if response.status_code == 401:
                print("Warning: Authentication failed. Check username/password.")

            return False
        except Exception as e:
            print(f"WP Connection Error: {e}")
            return False

    def upload_draft(self, title: str, content: str, excerpt: str = "", status: str = "draft", categories: List[int] = None, tags: List[int] = None) -> Optional[Dict]:
        """
        Uploads a post to WordPress.
        """
        data = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status
        }
        
        if categories:
            data["categories"] = categories
        if tags:
            data["tags"] = tags

        try:
            url = f"{self.api_url}/posts"
            print(f"Creating post: {url}")
            response = requests.post(url, auth=self.auth, headers=self.headers, json=data)
            
            if response.status_code != 201:
                print(f"Post Creation Failed: {response.status_code}")
                print(f"Response: {response.text}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error uploading to WordPress: {e}")
            if 'response' in locals() and response:
                print(f"Response: {response.text}")
            return None

    def upload_media(self, file_path: str, caption: str = "", description: str = "") -> Optional[Dict]:
        """
        Uploads an image to the WordPress Media Library.
        """
        if not file_path:
            return None
            
        filename = file_path.split("/")[-1]
        extension = filename.split(".")[-1].lower()
        mime_type = "image/jpeg"
        if extension == "png":
            mime_type = "image/png"
        elif extension == "gif":
            mime_type = "image/gif"
            
        try:
            with open(file_path, "rb") as img:
                data = img.read()
                
            print(f"Uploading media: {file_path}")
            
            upload_headers = self.headers.copy()
            upload_headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            upload_headers['Content-Type'] = mime_type

            response = requests.post(
                f"{self.api_url}/media",
                auth=self.auth,
                headers=upload_headers,
                data=data
            )
            
            if response.status_code != 201:
                print(f"Media Upload Failed: {response.status_code}")
                print(f"Response: {response.text}")
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error uploading media: {e}")
            return None
            
    def update_post_featured_media(self, post_id: int, media_id: int) -> bool:
        """
        Sets the featured image for a post.
        """
        try:
            url = f"{self.api_url}/posts/{post_id}"
            print(f"Setting featured media {media_id} for post {post_id}")
            response = requests.post(
                url,
                auth=self.auth,
                headers=self.headers,
                json={"featured_media": media_id}
            )
            
            if response.status_code != 200:
                print(f"Update Post Media Failed: {response.status_code}")
                print(f"Response: {response.text}")

            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error setting featured image: {e}")
            return False
