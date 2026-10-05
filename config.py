"""Конфиг самообучающегося бота. Читает .env"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Через запятую: 123456789,987654321
_owner_raw = os.getenv("OWNER_IDS", "").strip()
OWNER_IDS: set[int] = set()
if _owner_raw:
    for part in _owner_raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            OWNER_IDS.add(int(part))

# Ключ Gemini (то, что ты прислал AQ...). FolderId больше не нужен.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

SKILLS_DIR = BASE_DIR / "skills"
SKILLS_DIR.mkdir(exist_ok=True)
MANIFEST = SKILLS_DIR / "skills.json"

# Только эти импорты разрешены в генерируемом коде навыков (безопасность)
ALLOWED_IMPORTS = {
    "re", "random", "datetime", "json", "math",
    "aiogram", "aiogram.types", "aiogram.enums",
}
