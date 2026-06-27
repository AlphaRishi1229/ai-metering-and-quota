from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    USE_REAL_LLM: bool = False
    ANTHROPIC_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
