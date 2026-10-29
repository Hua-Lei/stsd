from pydantic import BaseSettings  

class GeneratorConfig(BaseSettings):
    api_key: str
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.ai"
    max_tokens: int = 32000
    timeout: int = 10