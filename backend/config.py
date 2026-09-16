import sys
from pydantic_settings import BaseSettings
from pathlib import Path

if getattr(sys, "frozen", False):
    # Packaged exe: keep user data next to the .exe itself (portable, writable, persists across runs)
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.parent  # repo root, or a source bundle's root

# Needed on any fresh checkout/bundle that doesn't already have these (a git
# clone ships profile/profile.example.json but not profile/profile.json itself,
# and a stripped-down source bundle may ship neither dir at all) — profile
# writes and the sqlite db would otherwise fail with "no such file or directory".
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "profile").mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gmail_app_password: str = ""
    gmail_from: str = ""
    rapidapi_key: str = ""

    scan_interval_hours: int = 6
    max_jobs_per_scan: int = 50

    # Daily digest email (sent after each scheduled scan)
    digest_enabled: bool = True
    digest_to: str = ""          # falls back to gmail_from
    frontend_url: str = "http://localhost:3000"

    @property
    def digest_recipient(self) -> str:
        return self.digest_to or self.gmail_from

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

    @property
    def frontend_dist_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / "frontend_out"   # bundled read-only data, see pyinstaller --add-data
        return BASE_DIR / "frontend" / "out"              # dev: wherever `npm run build` wrote the static export

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"


settings = Settings()
