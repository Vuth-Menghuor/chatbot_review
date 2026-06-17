"""Configuration management for Trade Query Service."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class Settings:
    """Env-driven settings."""

    def __init__(self, env_file: Optional[Path] = None):
        if env_file and env_file.exists():
            load_dotenv(env_file)
        else:
            # Load service-specific environment variables first
            local_env = Path(__file__).resolve().parent / ".env"
            if local_env.exists():
                load_dotenv(local_env)
            else:
                load_dotenv()

        self.dal_base_url = os.getenv("DAL_BASE_URL", "http://localhost:8000")
        self.dal_api_key = os.getenv("DAL_API_KEY", "")
        self.dal_dataset_code = os.getenv("DAL_DATASET_CODE", "trade_volume")

        self.host = os.getenv("TRADE_SERVICE_HOST", "0.0.0.0")
        self.port = int(os.getenv("TRADE_SERVICE_PORT", "8005"))

        self.rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
        self.max_payload_size_mb = int(os.getenv("MAX_PAYLOAD_SIZE_MB", "1"))
        self.allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")


def get_settings() -> Settings:
    return Settings()
