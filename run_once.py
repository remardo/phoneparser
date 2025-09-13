import asyncio
from telethon import TelegramClient
from src.google_sheets import update_phones
from src.utils import load_json

BOT_USERNAME = "@UssboxBot"

async def main():
    sessions = load_json()
    # use first session only
    session_name, items = next(iter(sessions.items()))
    client = TelegramClient(session_name, items[0], items[1], system_version="4.16.30-vxCUSTOM")
    async with client:
        chat_entity = await client.get_entity(BOT_USERNAME)
        await update_phones(chat_entity, client, max_rows=1)

if __name__ == "__main__":
    asyncio.run(main())
