from crewai import LLM
from clef_app.config import ConfigManager

def get_llm(model: str = None, temperature: float = None):
    config = ConfigManager()
    
    # Load API keys to environment if needed, or rely on .env
    # The original script uses load_dotenv().
    # Here we might need to set them from config if not in env.
    api_keys = config.get("api_keys", {})
    if api_keys.get("openai_api_key"):
        import os
        os.environ["OPENAI_API_KEY"] = api_keys["openai_api_key"]
    
    settings = config.get("settings", {})
    
    model_name = model or settings.get("llm_model", "openai/gpt-4.1")
    temp = temperature if temperature is not None else settings.get("llm_temperature", 0.3)
    
    return LLM(model=model_name, temperature=temp)
