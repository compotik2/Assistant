@echo off
cd /d %~dp0
python -m pip install -r requirements.txt
if not exist .env copy /Y .env.example .env
echo Если первый запуск - открой .env и впиши BOT_TOKEN
pause
python bot.py
pause
