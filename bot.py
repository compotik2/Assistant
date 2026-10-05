"""Самообучающийся Telegram-бот для групп.
Добавь в группу, дай права админа (если нужны темы/удаление),
и пиши: научись распределять сообщения / /learn ...

Учат бота ТОЛЬКО владелец (OWNER_IDS) и админы чата.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

import config
from config import BOT_TOKEN, OWNER_IDS, SKILLS_DIR
from skill_manager import load_all_skills, safe_check, save_skill, delete_skill, _load_module
from brain import generate_skill_code

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("evolve-bot")

SKILLS = {}  # name -> Skill

# ---------- права ----------

async def is_privileged(message: Message, bot: Bot) -> bool:
    # Проверка ID отключена по просьбе владельца — учить может любой.
    return True


def should_react(message: Message, bot: Bot) -> bool:
    """В группах реагируем на: команды, упоминание бота, реплай, слово 'научись'."""
    if message.chat.type == "private":
        return True
    text = (message.text or message.caption or "").lower()
    if text.startswith("/"):
        return True
    if "научись" in text or "научи " in text or "забудь" in text:
        return True
    # упомянули бота?
    try:
        me = getattr(bot, "_me_username", "")
        if me and f"@{me.lower()}" in text:
            return True
    except Exception:
        pass
    if message.reply_to_message and message.reply_to_message.from_user:
        try:
            if message.reply_to_message.from_user.id == bot.id:
                return True
        except Exception:
            pass
    return False


# ---------- обучение ----------

async def do_learn(message: Message, bot: Bot, task: str):
    status = await message.reply("🧠 Учусь... пишу код навыка...")
    try:
        existing = list(SKILLS.keys())
        result = await generate_skill_code(task, existing)
        name, code, desc = result["name"], result["code"], result["description"]

        ok, reason = safe_check(code)
        if not ok:
            await status.edit_text(f"⛔ Сгенерировал небезопасный код и отклонил его: {reason}")
            return

        path = save_skill(name, code)
        try:
            mod = _load_module(name, path)
            # пробный вызов контракта
            assert hasattr(mod, "handle"), "нет handle()"
            from skill_manager import Skill
            SKILLS[name] = Skill(
                name=getattr(mod, "SKILL_NAME", name),
                description=getattr(mod, "SKILL_DESCRIPTION", desc),
                triggers=list(getattr(mod, "TRIGGERS", [])),
                module=mod, path=path,
            )
        except Exception as e:
            path.unlink(missing_ok=True)
            await status.edit_text(f"⚠️ Код не запустился, откатил: {e}")
            return

        await status.edit_text(
            f"✅ Научился! Навык <code>{name}</code>\n"
            f"📝 {desc}\n"
            f"⚡ Триггеры: {', '.join(SKILLS[name].triggers[:8]) or '—'}\n"
            f"Посмотреть код: <code>/code {name}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.exception("learn fail")
        await status.edit_text(f"❌ Не получилось научиться: {e}")


# ---------- запуск ----------

async def main():
    if not BOT_TOKEN:
        print("❌ Нет BOT_TOKEN в .env. Получи у @BotFather и впиши в .env")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    me = await bot.get_me()
    bot._me_username = (me.username or "").lower()
    print(f"Бот @{me.username} запущен. Добавь его в группу.")

    global SKILLS
    SKILLS = load_all_skills()
    print(f"Загружено навыков: {list(SKILLS)}")

    @dp.message(Command("start", "help"))
    async def cmd_start(message: Message):
        await message.answer(
            "👋 Я <b>самообучающийся бот</b> для групп.\n\n"
            "Меня можно добавить в группу и учить новым фишкам:\n"
            "• <code>научись распределять сообщения</code>\n"
            "• <code>/learn отвечай на спасибо стикером</code>\n"
            "• <code>/skills</code> — что я уже умею\n"
            "• <code>/code имя</code> — показать код навыка\n"
            "• <code>/forget имя</code> — забыть навык\n\n"
            "Учить меня может любой.",
        )

    @dp.message(Command("skills"))
    async def cmd_skills(message: Message):
        if not SKILLS:
            await message.answer("Пока ничего не умею. Напиши: <code>научись ...</code>")
            return
        lines = [f"• <code>{n}</code> — {s.description} (триггеры: {', '.join(s.triggers[:5])})"
                 for n, s in SKILLS.items()]
        await message.answer("🧩 Мои навыки:\n" + "\n".join(lines))

    @dp.message(Command("learn"))
    async def cmd_learn(message: Message):
        if not await is_privileged(message, bot):
            await message.reply("⛔ Учить меня могут только админы группы или владелец.")
            return
        task = (message.text or "").split(maxsplit=1)
        if len(task) < 2 or len(task[1].strip()) < 3:
            await message.reply("Напиши так: <code>/learn распределять сообщения по темам</code>")
            return
        await do_learn(message, bot, task[1].strip())

    @dp.message(Command("forget", "delete"))
    async def cmd_forget(message: Message):
        if not await is_privileged(message, bot):
            await message.reply("⛔ Только админы.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Напиши: <code>/forget имя_навыка</code>")
            return
        name = parts[1].strip().lower()
        if name in SKILLS:
            del SKILLS[name]
        if delete_skill(name):
            await message.answer(f"🗑️ Забыл навык <code>{name}</code>")
        else:
            await message.answer("Такого навыка нет. Список: /skills")

    @dp.message(Command("code"))
    async def cmd_code(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("Напиши: <code>/code имя_навыка</code>")
            return
        name = parts[1].strip().lower()
        path = SKILLS_DIR / f"{name}.py"
        if not path.exists():
            await message.answer("Нет такого файла.")
            return
        code = path.read_text(encoding="utf-8")[:3800]
        await message.answer(f"<pre>{code.replace('<','&lt;')}</pre>")

    # естественное "научись ..."
    @dp.message(F.text.lower().startswith(("научись", "научи ", "научи,")))
    async def natural_learn(message: Message):
        if not should_react(message, bot):
            return
        if not await is_privileged(message, bot):
            await message.reply("⛔ Меня могут учить только админы. Попроси админа написать это.")
            return
        task = message.text.strip()
        # убрать само слово "научись"
        for p in ("научись", "научи"):
            if task.lower().startswith(p):
                task = task[len(p):].strip(" ,:—-")
                break
        if len(task) < 3:
            await message.reply("Чему научить? Пример: <code>научись распределять сообщения</code>")
            return
        await do_learn(message, bot, task)

    @dp.message(F.text.lower().startswith(("забудь", "удали навык")))
    async def natural_forget(message: Message):
        if not await is_privileged(message, bot):
            return
        # "забудь distribute"
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            name = parts[1].strip().lower().split()[0]
            if name in SKILLS:
                del SKILLS[name]
            if delete_skill(name):
                await message.answer(f"🗑️ Забыл <code>{name}</code>")

    # главный роутер навыков — последним!
    @dp.message()
    async def router(message: Message):
        # команды уже обработаны выше, но если не среагировали — выходим в группах без упоминания
        text = (message.text or message.caption or "")
        if not text:
            return
        if message.chat.type in ("group", "supergroup") and not should_react(message, bot):
            # навыки с триггерами всё равно проверяем тихо (для распределения сообщений)
            pass

        for name, skill in list(SKILLS.items()):
            try:
                low = text.lower()
                # быстрый префильтр по триггерам
                if skill.triggers and not any(t.lower() in low for t in skill.triggers):
                    continue
                handled = await skill.module.handle(message, bot)
                if handled:
                    break
            except Exception as e:
                log.exception(f"skill {name} упал: {e}")
                continue

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
