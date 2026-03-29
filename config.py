from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required
    openai_api_key: SecretStr
    github_token: SecretStr

    # Optional with defaults
    openai_model: str = "gpt-4.1-mini"
    log_level: str = "INFO"
    request_timeout: int = 30
    best_practices_urls: list[str] = [
        "https://raw.githubusercontent.com/cjdava/best-practices/main/code-peer-review.md"
    ]

    @field_validator("best_practices_urls", mode="before")
    @classmethod
    def parse_urls(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [url.strip() for url in v.split(",") if url.strip()]
        return v


settings = Settings()
