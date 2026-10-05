SKILL_NAME = "distribute"
SKILL_DESCRIPTION = "Распределяет сообщения по типам: вопрос, мем, новость, важно"
TRIGGERS = ["вопрос", "мем", "новость", "важно", "?"]

async def handle(message, bot):
    text = ((message.text or message.caption) or "").lower()
    if not text:
        return False
    if "?" in text or "вопрос" in text:
        await message.reply("❓ Принято как <b>вопрос</b>. Передал знатокам.", parse_mode="HTML")
        return True
    if "мем" in text:
        await message.reply("😂 Принято как <b>мем</b>.", parse_mode="HTML")
        return True
    if "новость" in text:
        await message.reply("📰 Принято как <b>новость</b>.", parse_mode="HTML")
        return True
    if "важно" in text or "срочно" in text:
        await message.reply("🚨 Помечено как <b>важное</b>.", parse_mode="HTML")
        return True
    return False
