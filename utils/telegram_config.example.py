"""Example Telegram configuration template for fresh Hummingbird / Potato Farm nodes.

Copy to utils/telegram_config.py (which is gitignored) or set environment variables:
  HB_TELEGRAM_BOT_TOKEN=<your_bot_token>
  HB_TELEGRAM_OWNER_CHAT_IDS=<comma_separated_chat_ids>
"""
import os

BOT_TOKEN = os.environ.get('HB_TELEGRAM_BOT_TOKEN', '')
OWNER_CHAT_IDS = [
    int(x.strip())
    for x in os.environ.get('HB_TELEGRAM_OWNER_CHAT_IDS', '').split(',')
    if x.strip().isdigit()
]
