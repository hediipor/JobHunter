from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # D:\jobhunter


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gmail_app_password: str = ""
    gmail_from: str = ""
    rapidapi_key: str = ""

    scan_interval_hours: int = 6
    max_jobs_per_scan: int = 50

    @property
    def database_url(self) -> str:
        return f"sqlite:///{BASE_DIR / 'data' / 'jobhunter.db'}"

    @property
    def generated_dir(self) -> Path:
        d = BASE_DIR / "data" / "generated"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def profile_path(self) -> Path:
        return BASE_DIR / "profile" / "profile.json"

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


settings = Settings()
