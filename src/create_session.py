import re
from src.utils import load_json, dump_json, logger
from telethon import TelegramClient

data = load_json()  # данные наших сессий
if any(data):
    last_session = list(data)[-1]
    match = re.search(r"(\d+)$", last_session)
    session_num = int(match.group(1)) + 1
else:
    session_num = 1

SESSION_NAME = f"session{session_num}"
API_ID = int(input("Enter API_ID: "))
API_HASH = str(input("Enter API_HASH: "))

client = TelegramClient(SESSION_NAME, API_ID, API_HASH, system_version="4.16.30-vxCUSTOM")


async def check_account():
    async with client:
        me = await client.get_me()
        logger.info(f"Add session | Number: {SESSION_NAME} | Username: {me.username}")
        data[SESSION_NAME] = [API_ID, API_HASH]
        dump_json(data)


client.loop.run_until_complete(check_account())
