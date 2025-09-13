import asyncio
import os
import random

from telethon import TelegramClient

from src.google_sheets import update_phones
from src.utils import load_json, logger

BOT_USERNAME = "@UssboxBot"  # юзернейм бота, откуда будем получать инфу


async def main():
    while True:
        sessions = load_json()

        for session_name, items in sessions.items():
            logger.info(f"Подключение к {session_name} | всего сессий [{len(sessions)}]")
            # Ensure dedicated sessions directory exists and use it for .session files
            os.makedirs("sessions", exist_ok=True)
            session_path = os.path.join("sessions", session_name)

            client = TelegramClient(session_path, items[0], items[1], system_version="4.16.30-vxCUSTOM")
            async with client:
                chat_entity = await client.get_entity(BOT_USERNAME)
                try:
                    await update_phones(chat_entity, client, session_name=session_name)
                except Exception as e:
                    logger.exception(e)

                session_cooldown = random.randint(45, 100)
                logger.info(f"Сессия {session_name} достиг суточного лимита в боте, кулдаун {session_cooldown} секунд перед следующей сессией")
                await asyncio.sleep(session_cooldown)

        event_cooldown = random.randint(14 * 60 * 60, 26 * 60 * 60)
        logger.info(f"Все сессии достигли суточного лимита в боте, кулдаун {event_cooldown / 60 / 60} часа перед следующим циклом")
        await asyncio.sleep(event_cooldown)
        continue


if __name__ == "__main__":
    asyncio.run(main())
