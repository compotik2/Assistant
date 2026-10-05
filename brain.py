"""Генерация кода навыков через Gemini + fallback без LLM."""
import aiohttp
import re
import json

from config import GEMINI_API_KEY, GEMINI_MODEL

SYSTEM_PROMPT = """Ты — генератор навыков для Telegram-бота на aiogram 3.x.
Твоя задача: по описанию пользователя сгенерировать ОДИН Python-файл навыка.

СТРОГИЙ КОНТРАКТ ФАЙЛА (иначе бот его отклонит):
SKILL_NAME = "короткое_имя_латиницей_без_пробелов"
SKILL_DESCRIPTION = "что делает навык, по-русски"
TRIGGERS = ["слово1", "слово2"]

async def handle(message, bot):
    # message: aiogram.types.Message, bot: aiogram.Bot
    # Верни True если обработал, False если пропустил.
    # Внутри можно использовать только: await message.reply(...), await message.answer(...)
    # НЕ используй: os, sys, subprocess, socket, open(), requests, eval, exec.
    ...

Правила:
1. Только разрешённые импорты: re, random, datetime, json, math, aiogram
2. Никаких токенов и ключей в коде.
3. Код короткий (до 80 строк), без бесконечных циклов и while.
4. TRIGGERS — обязательно, минимум 1 триггер на русском.
5. handle() обязана быть async.
6. Верни ТОЛЬКО валидный Python-код, без пояснений. Можно обернуть в ```python.
"""

def _slugify(task: str) -> str:
    s = task.lower()
    s = re.sub(r"[^a-zа-я0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    trans = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z",
             "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
             "с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch",
             "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"}
    out = "".join(trans.get(c, c) for c in s)
    out = re.sub(r"[^a-z0-9_]+", "", out).strip("_")
    return (out[:30] or "skill").strip("_")


def template_skill(task: str) -> dict:
    name = _slugify(task)
    stop = {"научись","научи","распределять","распредели","сообщения","сообщение",
            "пожалуйста","бот","меня","как","делать","это","для","и","в","на"}
    words = [w.strip(".,!?;:") for w in task.lower().split()]
    triggers = [w for w in words if len(w) > 3 and w not in stop][:5] or ["важно"]
    trig_repr = json.dumps(triggers, ensure_ascii=False)
    code = f'''SKILL_NAME = "{name}"
SKILL_DESCRIPTION = "Авто-навык по задаче: {task[:80]}"
TRIGGERS = {trig_repr}

async def handle(message, bot):
    text = ((message.text or message.caption) or "").lower()
    if not text:
        return False
    for t in TRIGGERS:
        if t.lower() in text:
            await message.reply(
                f"🏷️ Распределено как <b>{{t}}</b> (навык <code>{name}</code>).",
                parse_mode="HTML"
            )
            return True
    return False
'''
    return {"name": name, "description": f"Авто-навык: {task[:80]}", "code": code, "triggers": triggers}


def _parse_code(text: str, task: str) -> dict:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    code = m.group(1).strip() if m else text.strip()
    # иногда Gemini добавляет текст до/после — режем до SKILL_NAME
    idx = code.find("SKILL_NAME")
    if idx > 0:
        code = code[idx:]
    n = re.search(r'SKILL_NAME\s*=\s*["\']([^"\']+)["\']', code)
    name = re.sub(r"[^a-z0-9_]", "", (n.group(1).lower() if n else _slugify(task)))
    if not name:
        name = _slugify(task)
    d = re.search(r'SKILL_DESCRIPTION\s*=\s*["\']([^"\']+)["\']', code)
    desc = d.group(1) if d else task[:100]
    t = re.search(r"TRIGGERS\s*=\s*(\[.*?\])", code, re.S)
    try:
        triggers = json.loads(t.group(1).replace("'", '"')) if t else []
    except Exception:
        triggers = []
    return {"name": name, "description": desc, "code": code, "triggers": triggers}


async def generate_skill_code(task: str, existing: list) -> dict:
    """Пытается через Gemini, при ошибке — template_skill."""
    if not GEMINI_API_KEY:
        return template_skill(task)

    existing_txt = ", ".join(existing) if existing else "нет"
    user_text = f"Задача пользователя: {task}\nУже есть навыки: {existing_txt}\nСгенерируй файл навыка."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2000},
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(url, json=payload) as r:
                if r.status != 200:
                    txt = (await r.text())[:800]
                    print(f"[gemini] HTTP {r.status}: {txt} -> fallback на шаблон")
                    return template_skill(task)
                data = await r.json()
    except Exception as e:
        print(f"[gemini] ошибка сети: {e} -> fallback на шаблон")
        return template_skill(task)

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[gemini] плохой ответ: {e} -> fallback")
        return template_skill(task)

    return _parse_code(text, task)
