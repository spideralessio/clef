import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

DB_FILE = "clef.db"

class DatabaseManager:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Scraped Articles
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scraped_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal TEXT,
                title TEXT,
                url TEXT,
                date TEXT,
                slug TEXT,
                path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(journal, slug)
            )
        ''')

        # Proposals
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                category TEXT,
                theme TEXT,
                rationale TEXT,
                status TEXT DEFAULT 'pending', -- pending, approved, rejected, completed
                content_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Generated Articles
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generated_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER,
                title TEXT,
                slug TEXT,
                path TEXT,
                language TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(proposal_id) REFERENCES proposals(id)
            )
        ''')
        
        conn.commit()
        conn.close()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # --- Scraped Articles ---
    def add_scraped_article(self, journal: str, title: str, url: str, date: str, slug: str, path: str):
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT OR IGNORE INTO scraped_articles (journal, title, url, date, slug, path)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (journal, title, url, date, slug, path))
            conn.commit()
        finally:
            conn.close()

    def article_exists(self, url: str) -> bool:
        conn = self.get_connection()
        cursor = conn.execute("SELECT 1 FROM scraped_articles WHERE url = ?", (url,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_scraped_articles(self, days: int = None, journal: str = None) -> List[Dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM scraped_articles"
        params = []
        conditions = []
        
        if journal:
            conditions.append("journal = ?")
            params.append(journal)
            
        # Filter by days in Python to be safer against date format issues
        # date argument in add_scraped_article might not be strict YYYY-MM-DD
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
            
        query += " ORDER BY date DESC"
        
        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if days:
            from datetime import datetime, timedelta
            filtered = []
            cutoff_date = datetime.now() - timedelta(days=days)
            for row in rows:
                row_date_str = row['date']
                try:
                    # Attempt strict YYYY-MM-DD
                    row_dt = datetime.strptime(row_date_str, "%Y-%m-%d")
                    if row_dt >= cutoff_date:
                        filtered.append(row)
                except ValueError:
                    # If date parsing fails, maybe include it or check other formats?
                    # For now, if we can't parse, we might decide to include strictly or loosely.
                    # Let's try to be loose: if it looks recent or we can't parse, maybe keep it?
                    # Or simpler: Just return everything if parsing fails to avoid empty lists.
                    # Or better: Print a warning and include it.
                    print(f"Warning: Could not parse date '{row_date_str}' for article '{row['title']}'. Including it.")
                    filtered.append(row)
            return filtered
        
        return rows

    def get_article_details(self, slug: str, journal: str = None) -> Dict:
        """
        Retrieves full article details including content and metadata from disk.
        """
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM scraped_articles WHERE slug = ?"
        params = [slug]
        
        if journal:
            query += " AND journal = ?"
            params.append(journal)
            
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
            
        article_data = dict(row)
        path = article_data.get('path')
        
        # Load content from disk if path exists
        if path and os.path.exists(path):
            try:
                meta_path = os.path.join(path, "metadata.json")
                content_path = os.path.join(path, "content.txt")
                
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        article_data.update(meta) # Merge metadata
                        
                if os.path.exists(content_path):
                    with open(content_path, 'r', encoding='utf-8') as f:
                        article_data['content'] = f.read()
            except Exception as e:
                print(f"Error loading article files for {slug}: {e}")
                article_data['error'] = str(e)
                
        return article_data

    # --- Proposals ---
    def add_proposal(self, proposal_data: Dict):
        conn = self.get_connection()
        try:
            # Check if content_json is already in proposal_data (from Pydantic dict dumping)
            # If so, use it. If not, dump proposal_data.
            if 'content_json' in proposal_data:
                content_json_str = proposal_data['content_json']
                # Ensure it is a string
                if not isinstance(content_json_str, str):
                    content_json_str = json.dumps(content_json_str) 
            else:
                content_json_str = json.dumps(proposal_data)

            conn.execute('''
                INSERT INTO proposals (title, category, theme, rationale, content_json, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (
                proposal_data.get('title'),
                proposal_data.get('category'),
                proposal_data.get('theme'),
                proposal_data.get('rationale'),
                content_json_str
            ))
            conn.commit()
        finally:
            conn.close()

    def get_proposals(self, status: str = None) -> List[Dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM proposals"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        # Parse content_json back to dict
        for row in rows:
            if row['content_json']:
                row['content'] = json.loads(row['content_json'])
        conn.close()
        return rows

    def update_proposal_status(self, proposal_id: int, status: str):
        conn = self.get_connection()
        conn.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
        conn.commit()
        conn.close()

    def delete_proposal(self, proposal_id: int):
        conn = self.get_connection()
        conn.execute("DELETE FROM proposals WHERE id = ?", (proposal_id,))
        conn.commit()
        conn.close()

    # --- Generated Articles ---
    def add_generated_article(self, proposal_id: int, title: str, slug: str, path: str, language: str):
        conn = self.get_connection()
        conn.execute('''
            INSERT INTO generated_articles (proposal_id, title, slug, path, language)
            VALUES (?, ?, ?, ?, ?)
        ''', (proposal_id, title, slug, path, language))
        conn.commit()
        conn.close()
        
    def get_generated_articles(self) -> List[Dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM generated_articles ORDER BY created_at DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
