from pydantic_settings import BaseSettings, SettingsConfigDict


class GeneratorConfig(BaseSettings):
    """从环境变量读取：DEEPSEEK_API_KEY、DEEPSEEK_MODEL 等。"""
    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_")

    api_key: str
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    max_tokens: int = 32000
    timeout: float = 300  # LLM 调用的超时（秒），生成长输出要几分钟；不是执行器的单请求超时
