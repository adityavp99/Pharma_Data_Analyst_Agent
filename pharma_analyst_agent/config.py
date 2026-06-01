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
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_PLANNER_MODEL = os.getenv("OPENAI_PLANNER_MODEL", OPENAI_MODEL)
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", OPENAI_MODEL)
AI_SUMMARY_PROVIDER = os.getenv("AI_SUMMARY_PROVIDER", "").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_SUMMARY_MODEL = os.getenv("OPENROUTER_SUMMARY_MODEL", "deepseek/deepseek-v4-flash:free")
ENABLE_LLM_PLANNER = os.getenv("ENABLE_LLM_PLANNER", "true").strip().lower() in {"1", "true", "yes"}
OPENROUTER_PLANNER_MODEL = os.getenv("OPENROUTER_PLANNER_MODEL", "deepseek/deepseek-v4-flash:free")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", OPENROUTER_PLANNER_MODEL)
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Pharma Data Analyst Agent")
CUSTOM_OPENAI_CHAT_URL = os.getenv("CUSTOM_OPENAI_CHAT_URL", "")
CUSTOM_OPENAI_API_KEY = os.getenv("CUSTOM_OPENAI_API_KEY", "")
CUSTOM_OPENAI_API_KEY_HEADER = os.getenv("CUSTOM_OPENAI_API_KEY_HEADER", "api-key")
CUSTOM_OPENAI_PLANNER_MODEL = os.getenv("CUSTOM_OPENAI_PLANNER_MODEL", "")
CUSTOM_OPENAI_VISION_MODEL = os.getenv("CUSTOM_OPENAI_VISION_MODEL", CUSTOM_OPENAI_PLANNER_MODEL)
CUSTOM_OPENAI_MAX_TOKENS = int(os.getenv("CUSTOM_OPENAI_MAX_TOKENS", "1500"))

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SEMANTIC_LAYER_DIR = PROJECT_ROOT / "semantic_layer"
