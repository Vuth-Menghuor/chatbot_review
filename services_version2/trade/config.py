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

        # Centralized settings for dates, limits, and configurations
        self.min_available_year = int(os.getenv("MIN_AVAILABLE_YEAR", "2024"))
        self.max_available_year = int(os.getenv("MAX_AVAILABLE_YEAR", "2026"))
        self.default_suggestion_period = os.getenv("DEFAULT_SUGGESTION_PERIOD", "2026")
        
        # Load default suggestion countries list and pad to 3 to avoid downstream hardcoding
        raw_countries = os.getenv("DEFAULT_SUGGESTION_COUNTRIES", "China,Vietnam,Thailand")
        countries_list = [c.strip() for c in raw_countries.split(",") if c.strip()]
        if len(countries_list) < 3:
            std_countries = ["China", "Vietnam", "Thailand"]
            countries_list.extend(std_countries[len(countries_list):])
        self.default_suggestion_countries = countries_list

        self.default_gemini_model = os.getenv("DEFAULT_GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.default_timeout_sec = float(os.getenv("DEFAULT_TIMEOUT_SEC", "45.0"))

        self.dal_timeout = float(os.getenv("DAL_TIMEOUT", "20.0"))
        self.dal_max_retries = int(os.getenv("DAL_MAX_RETRIES", "3"))
        self.dal_backoff = float(os.getenv("DAL_BACKOFF", "1.0"))

        self.min_validation_year = int(os.getenv("MIN_VALIDATION_YEAR", "2000"))
        self.max_validation_year = int(os.getenv("MAX_VALIDATION_YEAR", "2100"))
        self.min_question_length = int(os.getenv("MIN_QUESTION_LENGTH", "5"))

        self.max_extraction_retries = int(os.getenv("MAX_EXTRACTION_RETRIES", "2"))
        self.max_chart_items = int(os.getenv("MAX_CHART_ITEMS", "15"))


def get_settings() -> Settings:
    return Settings()
