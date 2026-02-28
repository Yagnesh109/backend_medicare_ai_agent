from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com"
    allowed_origins: str = "*"
    request_timeout_seconds: int = 20
    public_base_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_voice_from_number: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def gemini_url(self) -> str:
        base = self.gemini_api_base.rstrip("/")
        model = self.gemini_model.strip()
        return f"{base}/v1beta/models/{model}:generateContent"

    @property
    def cors_origins(self) -> list[str]:
        raw = self.allowed_origins.strip()
        if not raw:
            return ["*"]
        if raw == "*":
            return ["*"]
        return [entry.strip() for entry in raw.split(",") if entry.strip()]


settings = Settings()

