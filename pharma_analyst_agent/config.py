from pathlib import Path
from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


DB_PATH = resolve_project_path(os.getenv("PHARMA_DB_PATH", "data/processed/pharma_mvp.db"))
MAX_SQL_ROWS = int(os.getenv("MAX_SQL_ROWS", "200"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
AI_SUMMARY_PROVIDER = os.getenv("AI_SUMMARY_PROVIDER", "").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_SUMMARY_MODEL = os.getenv("OPENROUTER_SUMMARY_MODEL", "deepseek/deepseek-v4-flash:free")

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SEMANTIC_LAYER_DIR = PROJECT_ROOT / "semantic_layer"
