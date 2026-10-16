import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MODEL_PATH = os.getenv("MODEL_PATH", "KULLANICI_ADIN/gemma3-tr-en-ceviri")
LOCAL_MODEL_PATH = BASE_DIR / "models" / "ceviri_modelim_v3"

CHROMA_DB_PATH = str(BASE_DIR / "chroma_db")
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

MAX_SEQ_LENGTH = 2048

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")