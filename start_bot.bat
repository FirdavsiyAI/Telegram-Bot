@echo off
REM ── Change this to where your bot lives:
cd /d C:\Users\User\Projects\telegram-bot

REM ── Activate your virtual environment:
call venv\Scripts\activate.bat

REM ── Run the bot (stays alive until you close the window):
python bot.py

