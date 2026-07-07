import pytest
from pathlib import Path
from dotenv import load_dotenv

# Automatically load the local service-specific environment variables for all tests in this directory
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()
