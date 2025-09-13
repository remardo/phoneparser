import asyncio
import os
import random
import traceback
import gspread
import re

from typing import Union, Optional, Dict, List
from bs4 import BeautifulSoup
from telethon import errors
from telethon.sync import TelegramClient
from telethon.tl.types import Message, MessageMediaDocument

from src.utils import logger

# TEST
# table_url = "https://docs.google.com/spreadsheets/d/1B0cCvLIzfVcKpCa3ioNK2lJCR47zNbt6povjV-DlXmM/edit?gid=2010924534#gid=2010924534"
# table_key = "1B0cCvLIzfVcKpCa3ioNK2lJCR47zNbt6povjV-DlXmM"
# worksheet_name = "report"

# WORK
table_url = "https://docs.google.com/spreadsheets/d/1y64pA_GnOPT2shVXHnwrfWDpeNq3vrdRv0RN-9dwljI/edit?usp=sharing"
table_key = "1y64pA_GnOPT2shVXHnwrfWDpeNq3vrdRv0RN-9dwljI"
worksheet_name = "Лист2"

gc = gspread.service_account("src/service-acount-sheets.json")
table = gc.open_by_key(table_key)

FIO_COL = 3
INN_COL = 4
PHONE_COL = 6
# Отдельный столбец для email адресов
EMAIL_COL = 7
COOLDOWN = (15, 30)
COOLDOWN_REQUEST = (30, 60)

ERROR_PATTERNS = [
    [re.compile(r"услов\w*.*бот.*подписк", re.I), "Условием данного бота является подписка на"],
    [re.compile(r"уч[её]тн\w*.запис\w*.*заблок", re.I), "Учетная запись заблокирована"],
    [re.compile(r"ваш\w*.*аккаунт\w*.*заблок", re.I), "Ваш аккаунт был заблокирован"],
    [re.compile(r"исчерпал\w*.*лимит\w*.*запрос", re.I), "Превышен дневной лимит запросов"]
]
PHONE_PATTERN = re.compile(r'\+\d{9,15}')
# Базовый паттерн email
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
BIRTHDAY_PATTERN = re.compile(
    r"(?:Даты рождения:|Дата рождения:)\s*[\n\r│├└─]*\s*(\d{2}\.\d{2}\.\d{4})"
)


def check_limit(messages: Message) -> Optional[str]:
    for message in messages:
        text = message.message

        for pattern, normalized_text in ERROR_PATTERNS:
            if pattern.search(text):
                return normalized_text

    return None


def generate_cooldown(request: bool = False):
    cooldown = random.randint(*COOLDOWN)
    if request:
        cooldown = random.randint(*COOLDOWN_REQUEST)

    logger.debug(f"Кулдаун перед следующим запросом - {cooldown}")

    return cooldown


def get_phone_numbers_and_birthdate_from_html(target_fullname: str, html_file_name: str):
    target_fullname_norm = re.sub(r'\s+', ' ', target_fullname.lower().strip())

    with open(html_file_name, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "html.parser")

    phones = set()
    emails = set()
    birth_date = None

    for card in soup.find_all("div", class_="card"):
        fio_parts = {"фамилия": "", "имя": "", "отчество": ""}
        full_name = ""

        for row in card.find_all("div", class_="row"):
            left = row.find("div", class_="row_left")
            right = row.find("div", class_="row_right")
            if not left or not right:
                continue

            label = left.text.strip().lower()
            value = right.text.strip()

            if "фио" in label:
                full_name = value
            elif "фамилия" in label:
                fio_parts["фамилия"] = value
            elif "имя" in label and "отчество" not in label:
                fio_parts["имя"] = value
            elif "отчество" in label:
                fio_parts["отчество"] = value

        if not full_name:
            full_name = " ".join(fio_parts.values()).strip()

        full_name_norm = re.sub(r'\s+', ' ', full_name.lower().strip())

        if target_fullname_norm in full_name_norm:
            for row in card.find_all("div", class_="row"):
                left = row.find("div", class_="row_left")
                right = row.find("div", class_="row_right")
                if not left or not right:
                    continue

                label = left.text.strip().lower()
                value = right.text.strip()

                if "телефон" in label:
                    raw_phones = value
                    possible_phones = re.split(r"[,\s]+", raw_phones)

                    for phone in possible_phones:
                        phone = phone.strip()
                        if PHONE_PATTERN.fullmatch(phone):
                            phones.add(phone)

                # Email может быть под разными лейблами
                elif ("email" in label) or ("e-mail" in label) or ("электрон" in label and "почт" in label):
                    for email in EMAIL_PATTERN.findall(value):
                        emails.add(email)
                elif "дата рождения" in label and not birth_date:
                    birth_date = value

            # На случай, если email указан где-то в блоке без явного лейбла
            block_text = card.get_text(" ")
            for email in EMAIL_PATTERN.findall(block_text):
                emails.add(email)

    return {
        "phones": list(phones),
        "emails": list(emails),
        "birthday": birth_date,
    }


async def get_phone_numbers_raw_inn(
    client: TelegramClient, chat, fio, inn
) -> Dict[str, Optional[Union[List[str], str]]]:
    """
    Если найдены номера телефонов, возвращает список из номеров как str и день рождения, если нету день рождения или номеров, то они None.
    """
    logger.debug(f"Поиск номера по ИНН: /raw {inn}")

    try:
        await client.send_message(chat, f"/raw {inn}")
        await asyncio.sleep(generate_cooldown())

        last_messages = await client.get_messages(chat, 2)
        check = check_limit(last_messages)
        if check:
            return {
                "phones": check,
                "emails": [],
                "birthday": None,
            }

        data = {
            "phones": [],
            "emails": [],
            "birthday": None,
        }

        for message in last_messages:
            if message.message and "ничего не найдено" in message.message:
                return data

            # Поиск номеров телефонов в тексте
            if message.message:
                matches = PHONE_PATTERN.findall(message.message)
                data['phones'].extend(matches)

                # Поиск email адресов в тексте
                email_matches = EMAIL_PATTERN.findall(message.message)
                data['emails'].extend(email_matches)

                # Поиск даты рождения
                birth_match = BIRTHDAY_PATTERN.search(message.message)
                if birth_match:
                    data['birthday'] = birth_match.group(1)

            # Если это html-документ
            if isinstance(message.media, MessageMediaDocument):
                file_path = await message.download_media()
                try:
                    if file_path and file_path.endswith('.html'):
                        logger.debug("HTML scrapping")
                        html_data = get_phone_numbers_and_birthdate_from_html(fio, file_path)
                        data['phones'].extend(html_data.get('phones', []))
                        data['emails'].extend(html_data.get('emails', []))
                        data['birthday'] = html_data.get('birthday')
                finally:
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)

        # Удаляем дубли и пробелы
        data['phones'] = list(set(num.strip() for num in data['phones'] if num.strip()))
        data['emails'] = list(set(e.strip() for e in data['emails'] if e.strip()))
        logger.debug(f"Найдено: {data['phones']}, emails: {data['emails']}, дата рождения: {data['birthday']}")

        return data

    except errors.FloodWaitError as e:
        logger.warning(f"FloodWaitError. Ждём {e.seconds} сек.")
        await asyncio.sleep(e.seconds + 10)
        return await get_phone_numbers_raw_inn(client, chat, fio, inn)

    except Exception as e:
        logger.exception(f"Неизвестная ошибка при поиске номеров. Краткое описание ошибки: {e}")
        return {
            "phones": [],
            "emails": [],
            "birthday": None,
        }


async def get_phone_numbers_fio_dr(
    client: TelegramClient, chat, fio, birthday
) -> Union[List[str], str]:
    """
    Если найдены номера телефонов, возвращает список из номеров как str, иначе пустой список.
    """
    logger.debug(f"Поиск номера по ФИО + ДР: {fio} {birthday}")

    try:
        await client.send_message(chat, f"{fio} {birthday}")
        await asyncio.sleep(generate_cooldown())

        last_messages = await client.get_messages(chat, 2)
        check = check_limit(last_messages)
        if check:
            return check

        phone_numbers = []

        for message in last_messages:
            if message.message and "ничего не найдено" in message.message:
                return []

            # Поиск номеров телефонов в тексте
            if message.message:
                matches = PHONE_PATTERN.findall(message.message)
                phone_numbers.extend(matches)

            # Если это html-документ
            if isinstance(message.media, MessageMediaDocument):
                file_path = await message.download_media()
                try:
                    if file_path and file_path.endswith('.html'):
                        html_data = get_phone_numbers_and_birthdate_from_html(fio, file_path)
                        phone_numbers.extend(html_data.get('phones', []))
                finally:
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)

        # Удаляем дубли и пробелы
        phone_numbers = list(set(num.strip() for num in phone_numbers if num.strip()))
        logger.debug(f"Найдено: {phone_numbers}")

        return phone_numbers

    except errors.FloodWaitError as e:
        logger.warning(f"FloodWaitError. Ждём {e.seconds} сек.")
        await asyncio.sleep(e.seconds + 10)
        return await get_phone_numbers_fio_dr(client, chat, fio, birthday)

    except Exception as e:
        logger.exception(f"Неизвестная ошибка при поиске номеров. Краткое описание ошибки: {e}")
        return []


async def update_phones(
    chat,
    client: TelegramClient,
    max_rows: Optional[int] = None,
    session_name: Optional[str] = None,
) -> None:
    wks = table.worksheet(worksheet_name)
    fio_col_values = wks.col_values(FIO_COL)
    inn_col_values = wks.col_values(INN_COL)
    phone_col_values = wks.col_values(PHONE_COL)
    # Читаем текущую колонку email для возможной валидации или будущего использования
    try:
        email_col_values = wks.col_values(EMAIL_COL)
    except Exception:
        # Если лист пуст в этой колонке — продолжим без чтения
        email_col_values = []
    # Установим заголовок для столбца email при необходимости
    try:
        header_email = wks.cell(1, EMAIL_COL).value
        if not header_email or not header_email.strip():
            wks.update_cell(1, EMAIL_COL, "Email")
    except Exception:
        pass

    index = 2
    processed = 0
    while index <= len(inn_col_values):
        try:
            # Determine current cell values safely (lists can be shorter than total rows)
            phone_cell = phone_col_values[index - 1] if index - 1 < len(phone_col_values) else ""
            email_cell = email_col_values[index - 1] if index - 1 < len(email_col_values) else ""

            # Process row if phone is missing OR email is missing
            if (not phone_cell.strip()) or (not email_cell.strip()):
                logger.debug(f"Шаг [{index}/{len(inn_col_values)}]")
                current_fio = fio_col_values[index - 1]
                current_inn = inn_col_values[index - 1]
                phone_numbers = []

                raw_data = await get_phone_numbers_raw_inn(client, chat, current_fio, current_inn)
                phones = raw_data.get('phones')

                if not isinstance(phones, list):
                    logger.error(f"Ошибка не позволяющая работу сессии: {phones}")
                    return None

                phone_numbers.extend(phones)

                if raw_data.get('birthday'):
                    dr_phones = await get_phone_numbers_fio_dr(client, chat, current_fio, raw_data['birthday'])
                    if isinstance(dr_phones, str):
                        logger.warning(f"Не удалось получить телефоны по ФИО и дате рождения: {dr_phones}")
                    else:
                        phone_numbers.extend(dr_phones)

                phone_numbers = [
                    re.sub(r'^\+', '', number)
                    for number in phone_numbers
                    if not number.startswith('+380')
                ]
                phone_numbers_str = ', '.join(set(phone_numbers)) if phone_numbers else "телефон не найден"

                # Emails
                emails = raw_data.get('emails', [])
                emails_str = ', '.join(sorted(set(emails), key=str.lower)) if emails else "email не найден"

                # Обновляем обе колонки
                wks.update_cell(index, PHONE_COL, phone_numbers_str)
                wks.update_cell(index, EMAIL_COL, emails_str)
                logger.info(f"Добавлены значения: {current_fio} {current_inn} - phones: {phone_numbers_str} | emails: {emails_str} | Поле {index}")
                # METRIC: processed row
                logger.info(
                    f"[METRIC] processed row={{'row': {index}, 'fio': '{current_fio}', 'inn': '{current_inn}', 'session': '{session_name or ''}'}}"
                )
                await asyncio.sleep(generate_cooldown(True))
                processed += 1
                if max_rows is not None and processed >= max_rows:
                    break
        except Exception:
            logger.exception("Ошибка при обработке строки")
            traceback.print_exc()
            try:
                wks.update_cell(index, PHONE_COL, "ERROR")
                wks.update_cell(index, EMAIL_COL, "ERROR")
            except Exception:
                pass
            # METRIC: error row
            logger.error(f"[METRIC] error row={{'row': {index}, 'session': '{session_name or ''}'}}")

        index += 1

    return None
