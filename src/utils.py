import json
from sys import stderr
from loguru import logger

logger.remove()
logger.add("src/logs.log",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {line} - {message}",
           rotation="5 MB",
           compression="zip",
           level="DEBUG")


def load_json() -> dict:
    """
    Данные с 'src/sessions.json'

    {'session<номер сессий>': [апи_айди, 'апи_хэш', текущее_количество_совершенных_запросов_за_сегодня, максимально_допустимое_количество_запросов_за_этот_день], ...}
    {'session1': [48512348, 'cdsvjdvd4cas6c47848cdsc6c56', 0, 68], ...}
    """
    with open("src/sessions.json", "r", encoding='utf-8') as f:
        template = json.load(f)

    return template


def dump_json(template: dict):
    """
    Перезапись данных в 'src/sessions.json'
    """
    with open("src/sessions.json", "w", encoding="utf-8") as f:
        json.dump(template, f, indent=4, ensure_ascii=False)
