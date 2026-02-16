import json
import os
from typing import Dict, Any

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "api_keys": {
        "openai_api_key": "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"
    },
    "wordpress": {
        "url": "",
        "username": "",
        "application_password": ""
    },
    "settings": {
        "days_lookback": 7,
        "num_proposals": 5,
        "num_images": 1,
        "default_language": "italian",
        "llm_model": "openai/gpt-4.1",
        "llm_temperature": 0.3,
        "max_rpm": 10
    },
    "sources": {
        "Rolling Stone Italy": "https://www.rollingstone.it/musica/feed/",
        "Rolling Stone USA": "https://www.rollingstone.com/music/feed/"
    },
    "prompts": {
        "search_articles": "You are a precise article finder. Your sole responsibility is to visit a journal page, identify all articles published, and return a structured list with exact titles and URLs. You do NOT process the articles themselves.",
        "process_articles": "You are a meticulous content processor. For each article URL provided to you, you scrape the full text, generate a concise summary, determine the category and music style, extract metadata, and save everything.",
        "proposal_generation": "You create detailed proposals with proper citations using article slugs and dates. You always verify that referenced articles exist.",
        "plan_article": "You design structure and angle based on several source pieces.",
        "write_article": "You read the source texts and follow the plan carefully.",
        "marketing_strategy": "You craft hooks and visuals for music & culture pieces.",
        "edit_article": "You ensure coherence and alignment with the proposal.",
        "design_image": "You are an AI image generator for an independent music magazine with a sophisticated editorial vision. Your images must feel authentic, tactile, and artistically crafted - never obviously AI-generated."
    }
}

class ConfigManager:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return DEFAULT_CONFIG

    def save_config(self, config: Dict[str, Any]):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        self.config = config

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save_config(self.config)
