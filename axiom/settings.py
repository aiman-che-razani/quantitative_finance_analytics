from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    api_token: str = Field(min_length=24)
    data_root: Path = Path("data/platform")
    report_root: Path = Path("reports/platform")
    max_active_runs: int = Field(default=2, ge=1, le=8)
