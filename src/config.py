import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = os.getenv("MODEL_PATH", "KULLANICI_ADIN/gemma3-tr-en-ceviri")
LOCAL_MODEL_PATH = BASE_DIR / "models" / "ceviri_modelim_v3"  

CHROMA_DB_PATH = str(BASE_DIR / "chroma_db")
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

MAX_SEQ_LENGTH = 2048