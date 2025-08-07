# bot.py

import sqlite3
from telebot import TeleBot
from telebot.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, CHANNELS, REFERRAL_THRESHOLD, GROUP_INVITE_LINK

# ─── DATABASE SETUP ─────────────────────────────────────────────────────────────
db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
cursor = db.cursor()

# ensure tables exist
cursor.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    referrer_id INTEGER
);

CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    PRIMARY KEY (referrer_id, referred_id)
);
""")
db.commit()

def record_user(user_id: int, referrer_id: int = None):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)",
        (user_id, referrer_id),
    )
    db.commit()
    if referrer_id:
        cursor.execute(
            "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, user_id),
        )
        db.commit()

def check_membership(bot: TeleBot, user_id: int) -> bool:
    all_ok = True
    for name, url in CHANNELS:
        # 1) normalize the “username” portion
        chat_name = url.rstrip("/").rsplit("/", 1)[-1]
        if not chat_name.startswith("@"):
            chat_name = "@" + chat_name

        try:
            member = bot.get_chat_member(chat_name, user_id)
            print(f"[DEBUG] get_chat_member('{chat_name}', {user_id}) → {member.status}")
            if member.status not in ("member", "administrator", "creator"):
                all_ok = False
        except Exception as e:
            print(f"[ERROR] failed to fetch membership for {chat_name}: {e}")
            all_ok = False

    return all_ok

def count_qualified_referrals(bot: TeleBot, referrer_id: int) -> int:
    cursor.execute(
        "SELECT referred_id FROM referrals WHERE referrer_id = ?",
        (referrer_id,),
    )
    rows = cursor.fetchall()
    return sum(1 for r in rows if check_membership(bot, r["referred_id"]))

def is_eligible(bot: TeleBot, user_id: int) -> bool:
    return (
        check_membership(bot, user_id)
        and count_qualified_referrals(bot, user_id) >= REFERRAL_THRESHOLD
    )

bot = TeleBot(BOT_TOKEN)


def make_channel_keyboard():
    kb = InlineKeyboardMarkup()
    for idx, (name, url) in enumerate(CHANNELS, start=1):
        kb.add(InlineKeyboardButton(
            f"Subscribe to {name}", url=url
        ))
    # DONE button will just send us a callback to /check
    kb.add(InlineKeyboardButton("DONE ✅", callback_data="check"))
    return kb


@bot.message_handler(commands=["start"])
def on_start(msg: Message):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if ref == user_id:
        ref = None

    record_user(user_id, ref)

    text = (
        "👋 Welcome! To unlock your private link, please complete:\n\n"
        "1️⃣ Join all 4 channels below\n"
        "2️⃣ Invite 3 friends with your personal link:\n"
        f"   https://t.me/{bot.get_me().username}?start={user_id}\n\n"
        "When you’re done, tap DONE ✅ below."
    )
    bot.send_message(msg.chat.id, text, reply_markup=make_channel_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == "check")
def on_done(callback):
    user_id = callback.from_user.id
    if is_eligible(bot, user_id):
        bot.send_message(
            callback.message.chat.id,
            f"✅ Congratulations! Here’s your invite link:\n\n{GROUP_INVITE_LINK}"
        )
    else:
        missing = []
        if not check_membership(bot, user_id):
            missing.append("• You still need to join all 4 channels.")
        refs = count_qualified_referrals(bot, user_id)
        if refs < REFERRAL_THRESHOLD:
            missing.append(f"• Only {refs}/{REFERRAL_THRESHOLD} friends have joined.")
        text = "⚠️ You’re not quite there yet. Please complete:\n" + "\n".join(missing)
        bot.send_message(callback.message.chat.id, text)


if __name__ == "__main__":
    print("Bot started. Press Ctrl+C to stop.")
    bot.infinity_polling()
