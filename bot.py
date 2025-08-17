# bot.py

import sqlite3
from telebot import TeleBot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    BOT_TOKEN,
    CHANNELS,               # [("Label", "https://t.me/..."), ...]
    REFERRAL_THRESHOLD,     # 5
    GROUP_INVITE_LINK,      # "https://t.me/+VtfD9DoFZc0yYTdi"
    START_TEXT,             # long marketing text
)

# ─── DATABASE SETUP ─────────────────────────────────────────────────────────────
db = sqlite3.connect("bot.db", check_same_thread=False)
db.row_factory = sqlite3.Row
cursor = db.cursor()

cursor.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    referrer_id INTEGER
);

CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    PRIMARY KEY (referrer_id, referred_id)
);
""")
db.commit()


def record_user(user_id: int, referrer_id: int | None = None) -> None:
    """Insert the user; if a valid referrer is present, record the referral once."""
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


def _extract_chat_username(url: str) -> str | None:
    """
    Try to convert a t.me URL into something Bot API can check:
      - 'https://t.me/username'      -> '@username'
      - 'https://t.me/+InviteHash'   -> cannot be verified (returns None)
    Telegram's getChatMember requires @username or numeric chat_id, not invite links.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    # invite links like '+IbD0SWGSSiZkM2Ri' or 'joinchat/XXXX' cannot be validated
    if slug.startswith("+") or slug.lower().startswith("joinchat"):
        return None
    if slug.startswith("@"):
        return slug
    return f"@{slug}"


def check_membership(bot: TeleBot, user_id: int) -> bool:
    """
    Verify the user has joined all *verifiable* channels in CHANNELS.
    Channels given via invite links (t.me/+...) cannot be verified by the Bot API,
    so they are skipped from validation (we still show their Join buttons).
    """
    all_ok = True
    for name, url in CHANNELS:
        chat_name = _extract_chat_username(url)
        if chat_name is None:
            # We cannot verify invite links (t.me/+...), so we skip them here.
            print(f"[INFO] Skipping membership check for invite link: {url}")
            continue

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
    """
    Count referrals where the referred user *also* meets the channel-join requirement.
    """
    cursor.execute(
        "SELECT referred_id FROM referrals WHERE referrer_id = ?",
        (referrer_id,),
    )
    rows = cursor.fetchall()
    return sum(1 for r in rows if check_membership(bot, r["referred_id"]))


def is_eligible(bot: TeleBot, user_id: int) -> bool:
    """
    A user is eligible if they joined all verifiable channels and have at least
    REFERRAL_THRESHOLD qualified referrals.
    """
    return check_membership(bot, user_id) and (
        count_qualified_referrals(bot, user_id) >= REFERRAL_THRESHOLD
    )


bot = TeleBot(BOT_TOKEN)


def make_channel_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for name, url in CHANNELS:
        kb.add(InlineKeyboardButton(f"Join {name}", url=url))
    kb.add(InlineKeyboardButton("✅ I’ve completed", callback_data="check"))
    return kb


@bot.message_handler(commands=["start"])
def on_start(msg: Message) -> None:
    user_id = msg.from_user.id

    # optional ref argument: /start <referrer_id>
    args = msg.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if ref == user_id:
        ref = None

    record_user(user_id, ref)

    # Build personalized message: marketing text + referral link
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    text = (
        START_TEXT
        + "\n\n🔗 Your personal referral link:\n"
        + referral_link
        + "\n\n"
        f"• You must invite {REFERRAL_THRESHOLD} friends who also join these channels.\n"
        f"• When done, tap “✅ I’ve completed”."
    )

    bot.send_message(
        msg.chat.id,
        text,
        reply_markup=make_channel_keyboard(),
        disable_web_page_preview=True,
    )


@bot.callback_query_handler(func=lambda c: c.data == "check")
def on_done(callback) -> None:
    user_id = callback.from_user.id

    if is_eligible(bot, user_id):
        bot.send_message(
            callback.message.chat.id,
            f"✅ Congratulations! Here’s your invite link:\n\n{GROUP_INVITE_LINK}",
            disable_web_page_preview=True,
        )
        return

    # Build a helpful “what’s missing” message
    missing = []
    if not check_membership(bot, user_id):
        missing.append(f"• You still need to join all {len(CHANNELS)} channels.")
    refs = count_qualified_referrals(bot, user_id)
    if refs < REFERRAL_THRESHOLD:
        missing.append(f"• Only {refs}/{REFERRAL_THRESHOLD} friends have completed all steps.")

    text = "⚠️ You’re not quite there yet. Please complete:\n" + "\n".join(missing)
    bot.send_message(callback.message.chat.id, text, disable_web_page_preview=True)


if __name__ == "__main__":
    print("Bot started. Press Ctrl+C to stop.")
    bot.infinity_polling()
