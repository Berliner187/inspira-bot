#!/usr/bin/env python3
import json
import os
from csv import DictWriter, DictReader
import datetime
import re
import sys
import importlib
import locale
import tempfile
from time import time

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import InputFile
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from PIL import Image, ImageDraw, ImageFont
import io

import sqlite3
import aiosqlite


from config import config

from server_info import timing_decorator
from database_manager import INSPIRA_DB, UserManager, ProductManager, ReferralArrival, LimitedUsersManager
from secure import SecureDivision


__version__ = '0.0.1.1'
DEBUG = True


try:
    with open('config.json') as config_file:
        _config = json.load(config_file)
    exhibit = str(_config["telegram_beta_token"])
    admin_user_id = _config["admin_id"]
    PAYMENTS_TOKEN = _config["payment_token"]
except Exception as e:
    exhibit = None
    print("ОШИБКА при ЧТЕНИИ токена ТЕЛЕГРАМ", e)


bot = Bot(token=exhibit)
dp = Dispatcher(bot, storage=MemoryStorage())


# ============== КОНСТАНТЫ ===========================
FILE_LOG = 'log_file.dat'
FIELDS_LOG = ['date', 'time', 'user_id', 'point_entry', 'end_point', 'work_status']

# Локализация
locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')


# ============================================================================
# ------------------------- ЛИМИТ ЗАПРОСОВ от ПОЛЬЗОВАТЕЛЯ ---------------
user_requests = {}
REQUEST_LIMIT = 12
TIME_LIMIT = 32


notify_banned_users = []


# ===========================
# --- ШАБЛОННЫЕ СООБЩЕНИЯ ---
ADMIN_PREFIX_TEXT = '⚠ CONTROL PANEL ⚠\n'
PRODUCT_STATUSES = {
    "RECEIVED": "Получено ✅",
    "DONE": "Ожидает получения 🟡",
    "WORK": "В работе ⌛",
    "WAIT": "Ожидается ввод"
}
USER_PREFIX_TEXT = '<b>Уважаемый гость!</b>\n'


# Security
temporarily_blocked_users = {}
user_messages = {}


@timing_decorator
async def check_ban_users(user_id):
    # -------------------БАН ЮЗЕРОВ --------------

    check = await check_temporary_block(user_id)
    if check:
        return True

    result = await limited_users_manager.check_user_for_block(user_id)

    if result:
        if user_id not in notify_banned_users:
            await bot.send_message(
                admin_user_id,
                f"⚠ {user_id} VERSUCHT RAUS ZU KOMMEN\n\n"
            )
            await bot.send_message(
                user_id, f"╳ Der envLOUP1337-Algorithmus hat die Bedrohung erkannt und Sie zwangsweise blockiert. ╳\n\n"
                         f"🤡 <b>Die Entscheidung kann nicht angefochten werden. (T_T)</b> 🤡", parse_mode='HTML'
            )
            with open('media/img/T90.mp4', 'rb') as gif:
                await bot.send_animation(chat_id=user_id, animation=gif)

            notify_banned_users.append(user_id)
        return True


async def block_user_temporarily(user_id):
    temporarily_blocked_users[user_id] = datetime.datetime.now() + datetime.timedelta(minutes=30)
    await bot.send_message(
        user_id,
        f"Der envLOUP1337-Algorithmus hat ein abnormes Verhalten festgestellt, wodurch Sie Sie vorübergehend gesperrt wurden.\n\n"
        f"Entriegelungszeit: {temporarily_blocked_users[user_id]}", parse_mode='HTML')


async def check_temporary_block(user_id):
    if user_id in temporarily_blocked_users:
        if datetime.datetime.now() > temporarily_blocked_users[user_id]:
            del temporarily_blocked_users[user_id]
            return False
        else:
            return True
    else:
        return False


@timing_decorator
async def ban_request_restrictions(user_id):
    current_time = time()

    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id] = [t for t in user_messages[user_id] if current_time - t <= 30]
    user_messages[user_id].append(current_time)

    if len(user_messages[user_id]) >= REQUEST_LIMIT:
        if len(user_messages[user_id]) == TIME_LIMIT:
            await limited_users_manager.block_user(f"/ban {user_id}")
            await bot.send_message(admin_user_id, f"☠️ ORCHESTRA 🤙\n\n{user_id} ЛИКВИДИРОВАН ❌")
            write_log(f"USER {user_id}", "BAN")

        if await check_temporary_block(user_id) is False:
            await block_user_temporarily(user_id)
            user_messages[user_id] = []


@timing_decorator
async def check_user_in_db(message):
    user_id = message.from_user.id
    first_name = message.chat.first_name
    last_name = message.chat.last_name

    user_manager = UserManager(INSPIRA_DB)
    result = user_manager.check_user_in_database(user_id)

    if not result:
        _time_now = datetime.datetime.now().strftime('%H:%M %d-%m-%Y')
        user_data = {
            'user_id': message.from_user.id, 'fullname': message.chat.first_name,
            'phone': None, 'date_register': _time_now, 'user_status': 'active',
            'user_status_date_upd': _time_now, 'product_id': None
        }
        user_manager.add_record('users', user_data)

        product_user_data = {
            'product_id': None, 'status': None,
            'user_id': message.from_user.id, 'group_number': None,
            'status_update_date': _time_now
        }

        db_manager = ProductManager(INSPIRA_DB)
        db_manager.add_record('products', product_user_data)

        # Кнопка для администратора
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton("ДОБАВИТЬ ГОСТЯ", callback_data=f"fill_guest_card:{user_id}")
        markup.add(button)

        await bot.send_message(
            admin_user_id,
            f"⚠ NEW USER ⚠\n{first_name} {last_name} ({user_id})",
            reply_markup=markup
        )

    return result


# ============================================================================
# ------------------------- ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ -------------------------
@dp.message_handler(text='Запуск')
@dp.message_handler(text='Старт')
@dp.message_handler(text='Начать')
@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    if await check_ban_users(message.from_user.id) is not True:
        write_log(f"USER {message.from_user.id} in /start", "RUN")

        wait_message = await message.answer(
            "<b>➔ INSPIRA</b>\n"
            "Creative workshop\n\n"
            "<b>↧ DESIGN by </b>KOZAK\n",
            parse_mode='HTML'
        )
        await check_user_in_db(message)

        check_for_ref = message.text.split(' ')

        if len(check_for_ref) > 1:
            check_for_ref = check_for_ref[1]
            ref_manager = ReferralArrival(INSPIRA_DB)
            ref_manager.check_user_ref(message.from_user.id, check_for_ref)
            print("ID ARRIVAL:", check_for_ref, message.from_user.id)

        await asyncio.sleep(1)

        product_manager = ProductManager(INSPIRA_DB)
        product_manager.update_product_status(user_id=message.from_user.id, new_status="WAIT")
        product_status_by_user = product_manager.get_product_status(user_id=message.from_user.id)

        if product_status_by_user is not None:
            kb = [
                [
                    types.KeyboardButton(text="Узнать статус изделия"),
                ]
            ]
        else:
            kb = [
                [
                    types.KeyboardButton(text="Заполнить контактную информацию"),
                ]
            ]

        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await bot.send_photo(
            message.from_user.id, photo=InputFile('media/img/menu.png', filename='start_message.png'),
            reply_markup=keyboard, parse_mode='HTML',
            caption=f'<b>INSPIRA – искусство живет здесь.</b>\n\n'
                    f'Привет! Это Бот Inspira - тут ты можешь записаться на мастер-класс по гончарному делу, '
                    f'а также узнать о готовности твоего изделия')
        await wait_message.delete()


@dp.message_handler(lambda message: message.text == 'Заполнить контактную информацию')
async def product_status(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    phone_button = types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)
    keyboard.add(phone_button)

    await message.answer("Пожалуйста, отправьте свой номер телефона:", reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentType.CONTACT)
async def contact_handler(message: types.Message):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    first_name = message.from_user.first_name

    user_manager = UserManager(INSPIRA_DB)
    user_manager.update_contact_info(user_id=user_id, phone=phone)

    kb = [
        [
            types.KeyboardButton(text="Узнать статус изделия")
        ],
        [
            types.KeyboardButton(text="Больше"),
            types.KeyboardButton(text="Мои данные")
        ]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    await message.answer(f"Спасибо, {first_name}! Ваш номер телефона успешно получен.", reply_markup=keyboard)


@dp.message_handler(commands=['help'])
async def help_user(message: types.Message):
    write_log(f"USER {message.from_user.id} in Помощь", "TAP")
    # =========== ОГРАНИЧЕНИЯ на ЗАПРОСЫ ================
    if await check_ban_users(message.from_user.id) is not True:
        url_kb = InlineKeyboardMarkup(row_width=2)
        url_help = InlineKeyboardButton(text='Поддержка', url='https://taxi-watcher.ru')
        url_link = InlineKeyboardButton(text='Наш сайт', url='https://taxi-watcher.ru')
        url_kb.add(url_help, url_link)
        await message.answer(
            'Если возникли какие-либо трудности или вопросы, пожалуйста, ознакомьтесь со списком ниже',
            reply_markup=url_kb)


# =============================================================================
# --------------------------- НАВИГАЦИЯ ---------------------------------------
# --------------------- ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ --------------------------------
@dp.message_handler(commands=['status'])
@dp.message_handler(lambda message: message.text == 'Узнать статус изделия')
async def product_status(message: types.Message):

    db_manager = ProductManager(INSPIRA_DB)
    _status_product = db_manager.get_product_status(message.from_user.id)
    print(_status_product)

    if _status_product == 'WORK':
        await bot.send_message(
            message.from_user.id,
            'В РАБОТЕ ⌛\n\n<i>Вам придет уведомление, как только Ваше изделие будет готово.</i>', parse_mode='HTML'
        )

    elif _status_product == 'DONE':
        markup = InlineKeyboardMarkup()
        ready_button = InlineKeyboardButton(
            "ИЗДЕЛИЕ ПОЛУЧИЛ", callback_data=f"product_has_been_received:{message.from_user.id}")
        markup.add(ready_button)
        await bot.send_message(
            message.from_user.id, '<b>ГОТОВО ✅</b>\n\nМожете забрать свое творение!', reply_markup=markup,
            parse_mode='HTML'
        )

    elif _status_product == 'RECEIVED':
        await bot.send_message(
            message.from_user.id, '<b>ИЗДЕЛИЕ НА РУКАХ</b>\n\nПриходите к нам еще!', parse_mode='HTML'
        )

    elif _status_product == 'WAIT':
        await bot.send_message(
            message.from_user.id,
            '<b>ИЗДЕЛИЕ В ОЧЕРЕДИ</b>\n\nВам придет уведомление, когда Ваше изделие пойдет в работу.',
            parse_mode='HTML'
        )

    else:
        await bot.send_message(
            message.from_user.id, 'Статус не определен', parse_mode='HTML'
        )


def standard_datetime_format():
    return f"\n[{datetime.datetime.now().strftime('%H:%M:%S - %d.%m')}]"


def format_number(num):
    return '{0:,}'.format(num).replace(",", " ")


# ==========================================================================
# ------------------- РИСОВАНИЕ НА ИЗОБРАЖЕНИИ -----------------------------
@timing_decorator
async def process_image(message: types.Message, trip_info, status_track):
    write_log(f'process_image: {message.from_user.id}', 'START')
    image_path = 'img/template-error.png'
    _price_limit = ''
    _price_limit_color = '#967026'

    if type(trip_info) is int:
        print("process_image:", trip_info)
        write_log(f"USER {message.from_user.id}: type(trip_info) is int", "ERROR")
        await bot.send_message(
            message.from_user.id,
            f"Ошибка :(\n\nКод: {trip_info}\n\n"
            f"<i><a href={ERRORS_DOCU}>Коды ошибок</a></i>", parse_mode='HTML')
        return
    else:
        path_to_img = 'img/template-'

        if status_track == 'start':
            status = 'limit-set'
            _price_limit = f'> {user_prices[message.from_user.id]} {CURRENCY_DICT[trip_info[7]]}'  # ТУТ  message.price
            _price_limit_color = '#FF9797'
        elif status_track == 'finish':
            status = 'limit-done'
            _price_limit = f'{user_prices[message.from_user.id]} {CURRENCY_DICT[trip_info[7]]}'  # ТУТ  message.price
            _price_limit_color = '#19CA75'
        elif status_track == 'never-rich':
            status = 'limit-never-rich'
            _price_limit = f'{user_prices[message.from_user.id]} {CURRENCY_DICT[trip_info[7]]}'
            _price_limit_color = '#830E0E'
        else:
            status = 'limit-no'

        daytime = 'day'

        try:
            image_path = f'{path_to_img}{status}-{trip_info[6]}-{daytime}.png'
        except TypeError:
            print("process_image TypeError", "ERROR")
            await bot.send_message(
                message.from_user.id,
                f"Ошибка :(\n\nКод: {trip_info}\n\n"
                f"<i><a href={ERRORS_DOCU}>Коды ошибок</a></i>", parse_mode='HTML')
        except Exception as e:
            print("process_image", e, "ERROR")
            write_log(f"USER {message.from_user.id} in image_path: trip_info - {trip_info}: {e}", "ERROR")

    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    # try:
    font_bold_path = 'fonts/Involve-Medium.otf'
    font_semi_bold_path = 'fonts/Involve-Regular.otf'

    def draw_func(type_font, size_font, color, text_text, coord_x, coord_y):
        font = ImageFont.truetype(type_font, size_font)
        draw.text((coord_x, coord_y), text_text, font=font, fill=color)

    # Основная информация (стоимость)
    draw_func(font_bold_path, 160, '#484026', f'{trip_info[0]} {CURRENCY_DICT[trip_info[7]]}', 150, 1268)
    # Лимит, заданный пользователем
    draw_func(font_semi_bold_path, 96, _price_limit_color, _price_limit, 1080, 1256)
    # Основная информация (время поездки, расстояние, время ожидания)
    draw_func(font_semi_bold_path, 82, '#777366', trip_info[5], 1100, 1609)
    draw_func(font_semi_bold_path, 82, '#777366', trip_info[4], 610, 1609)
    draw_func(font_semi_bold_path, 82, '#777366', trip_info[2], 144, 1609)
    # Адреса
    saved_addresses = user_addresses[message.from_user.id].split(' в ')
    cur_address_1 = saved_addresses[0]
    cur_address_2 = saved_addresses[1]

    limit = 48

    if len(cur_address_1) > limit:
        format_str_address_1 = cur_address_1[:limit - 3] + '...'
    else:
        format_str_address_1 = cur_address_1

    if len(cur_address_2) > limit:
        format_str_address_2 = cur_address_2[:limit - 3] + '...'
    else:
        format_str_address_2 = cur_address_2

    draw_func(font_semi_bold_path, 48, '#2E2815', format_str_address_1, 142, 563)
    draw_func(font_semi_bold_path, 48, '#2E2815', format_str_address_2, 142, 646)

    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)

    kb = [
        [
            types.KeyboardButton(text="Переустановить лимит"),
        ],
        [
            types.KeyboardButton(text="Переустановить адреса"),
            types.KeyboardButton(text="Сбросить")
        ]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    if status_track == 'finish':
        lead_magnet_button = InlineKeyboardButton(
            text="🟢 Как менялась цена", callback_data="get_chart"
        )

        dynamic_graph_keyboard = InlineKeyboardMarkup().add(lead_magnet_button)

        await bot.send_photo(
            message.from_user.id, photo=InputFile(output, filename=f'{message.from_user.id}-edited_image.png'),
            parse_mode='HTML', reply_markup=dynamic_graph_keyboard,
            caption=f'⚡ <b>Цена снизилась до {trip_info[0]}</b> ⚡')

    elif status_track == 'no':
        kb = [
            [
                types.KeyboardButton(text="Задать лимит"),
            ],
            [
                types.KeyboardButton(text="Главная"),
                types.KeyboardButton(text="Сбросить"),
            ]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

        await bot.send_photo(
            message.from_user.id,
            photo=InputFile(output, filename=f'{message.from_user.id}edited_image.png'),
            parse_mode='HTML',
            reply_markup=keyboard,
            caption=f'<b><a href="https://3.redirect.appmetrica.yandex.com/route?start-lat={user_coordinates[message.from_user.id]["from"][0]}&start-lon={user_coordinates[message.from_user.id]["from"][1]}&end-lat={user_coordinates[message.from_user.id]["to"][0]}&end-lon={user_coordinates[message.from_user.id]["to"][1]}&level=50&ref=4217048&amp;appmetrica_tracking_id=1178268795219780156&lang=ru">ЗАКАЖИТЕ В ПРИЛОЖЕНИИ</a></b>\n\n'
                    f'<i>Можете задать свой лимит <b>по кнопке ниже ☟</b></i>')
    elif status_track == 'never-rich':
        kb = [
            [
                types.KeyboardButton(text="Статус отслеживания"),
            ],
            [
                types.KeyboardButton(text="Мои данные"),
                types.KeyboardButton(text="Сбросить"),
            ]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await bot.send_photo(
            message.from_user.id,
            photo=InputFile(output, filename=f'{message.from_user.id}never_rich_image.png'),
            parse_mode='HTML',
            reply_markup=keyboard,
            caption=f'<b>Отслеживание принудительно остановлено</b>\n\n'
                    f'<a href="https://3.redirect.appmetrica.yandex.com/route?start-lat={user_coordinates[message.from_user.id]["from"][0]}&start-lon={user_coordinates[message.from_user.id]["from"][1]}&end-lat={user_coordinates[message.from_user.id]["to"][0]}&end-lon={user_coordinates[message.from_user.id]["to"][1]}&level=50&ref=4217048&amp;appmetrica_tracking_id=1178268795219780156&lang=ru">ЗАКАЗАТЬ СЕЙЧАС</a>\n\n'
                    f'К сожалению, лимит для отслеживания на сегодня исчерпан :(\n\n'
                    f'<i><a href="{WHY_TRACKING_IS_STOP}">Почему это произошло?</a></i>')
    else:
        await bot.send_photo(message.from_user.id, photo=InputFile(output, filename=f'{message.from_user.id}_edited_image.png'))

    write_log(f'process_image: {message.from_user.id}', 'FINISH')


# ==========================================================================
# --------------------------- АДМИНАМ --------------------------------------
last_admin_message_id, last_admin_menu_message_id = {}, {}


# МЕХАНИЗМ УДАЛЕНИЯ СООБЩЕНИЯ (ИМИТАЦИЯ МЕНЮ для АДМИНА)
async def construction_to_delete_messages(message):
    try:
        if last_admin_message_id.get(message.from_user.id):
            await bot.delete_message(message.chat.id, last_admin_message_id[message.from_user.id])
        if last_admin_menu_message_id.get(message.from_user.id):
            await bot.delete_message(message.chat.id, last_admin_menu_message_id[message.from_user.id])
    except Exception:
        pass


async def drop_admin_message(message: types.Message, sent_message):
    last_admin_message_id[message.from_user.id] = sent_message.message_id
    last_admin_menu_message_id[message.from_user.id] = message.message_id


# Кнопки на админ-панели
ADMIN_PANEL_BUTTONS = [
        [
            types.KeyboardButton(text="/GROUPS/"),
            types.KeyboardButton(text="/2/"),
            types.KeyboardButton(text="/3/")
        ],
        [
            types.KeyboardButton(text="/USERS/"),
            types.KeyboardButton(text="/LOGS/"),
            types.KeyboardButton(text="/PC/")
        ]
    ]


@dp.message_handler(lambda message: message.text == 'ins2133')
@dp.message_handler(commands=['ins2133'])
async def admin_panel(message: types.Message):
    if message.from_user.id == admin_user_id:
        global ADMIN_PANEL_BUTTONS
        keyboard = types.ReplyKeyboardMarkup(keyboard=ADMIN_PANEL_BUTTONS, resize_keyboard=True)
        await message.reply("[INSPIRA] void [Admin]\n\n[ • Host-Launcher-Admin • ]", reply_markup=keyboard)
    else:
        await message.reply("Das Gefährlich. Makarov in Handschuhfach.")


@dp.callback_query_handler(lambda c: c.data.startswith('fill_guest_card:'))
async def process_fill_guest_card(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == admin_user_id:
        user_id = int(callback_query.data.split(':')[1])

        await bot.send_message(
            callback_query.from_user.id,
            f"Введите номер группы для {user_id}:"
        )

        @dp.message_handler(lambda message: message.text)
        async def process_group_number(message: types.Message):
            group_number = message.text

            db_manager = ProductManager(INSPIRA_DB)
            db_manager.update_user_group(user_id, group_number, "WORK")

            await bot.send_message(
                admin_user_id,
                f"{ADMIN_PREFIX_TEXT}"
                f"<b>ПРИНЯТО</b>\n\n"
                f"О пользователе {user_id}:\n"
                f"<i>-> Статус изделия: </i><b>В РАБОТЕ 🟡</b>\n"
                f"<i>-> Номер группы: </i><b>{group_number}</b>",
                parse_mode='HTML'
            )

            await bot.send_message(
                user_id,
                f"{USER_PREFIX_TEXT}\n"
                f"Ваше изделие принято в работу!",
                parse_mode='HTML'
            )

            markup = InlineKeyboardMarkup()
            ready_button = InlineKeyboardButton(
                "ЗАДАТЬ СТАТУС >ГОТОВО<", callback_data=f"set_status_ready:{user_id}")
            markup.add(ready_button)

            await bot.send_message(
                admin_user_id,
                f"Изменить статус изделия пользователя {user_id}",
                reply_markup=markup
            )


@dp.callback_query_handler(lambda c: c.data.startswith('bring_the_product_to_work:'))
async def bring_the_product_to_work(callback_query: types.CallbackQuery):
    # TODO: Связать с process_fill_guest_card
    if callback_query.from_user.id == admin_user_id:
        user_id = int(callback_query.data.split(':')[1])

        db_manager = ProductManager(INSPIRA_DB)
        db_manager.update_product_status(user_id, "WORK")
        _user_card = db_manager.get_user_card(user_id)

        await bot.send_message(
            admin_user_id,
            f"{ADMIN_PREFIX_TEXT}"
            f"<b>ПРИНЯТО В РАБОТУ</b>\n\n"
            f"• Статус изделия гостя: </i><b>{PRODUCT_STATUSES[_user_card['product_status']]}</b>\n"
            f"• Номер группы: </i><b>{_user_card['group_id']}</b>\n\n"
            f"<i>Обновлено {_user_card['update_product_status']}</i>",
            parse_mode='HTML'
        )

        await bot.send_message(
            user_id,
            f"<b>ПРИНЯТО</b>\n\n"
            f"Ваше изделие принято в работу!",
            parse_mode='HTML'
        )


@dp.callback_query_handler(lambda c: c.data.startswith('fill_guest_product_id:'))
async def process_fill_guest_product_id(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == admin_user_id:
        user_id = int(callback_query.data.split(':')[1])

        await bot.send_message(
            callback_query.from_user.id,
            f"ВВЕДИТЕ НОМЕР ГРУППЫ для {user_id}:"
        )

        @dp.message_handler(lambda message: message.text.isdigit())
        async def process_group_number(message: types.Message):
            group_number = message.text

            db_manager = ProductManager(INSPIRA_DB)
            db_manager.update_user_group(user_id, group_number, "WORK")

            markup = InlineKeyboardMarkup()
            ready_button = InlineKeyboardButton(
                "Изменить статус на 'готово'", callback_data=f"set_status_ready:{user_id}")
            markup.add(ready_button)

            await bot.send_message(
                admin_user_id,
                f"-> В РАБОТЕ 🟡\n"
                f"<i>Статус изделия для {user_id}</i>\n\n"
                f"-> Номер группы: {group_number}",
                reply_markup=markup
            )


@dp.callback_query_handler(lambda c: c.data.startswith('set_status_ready:'))
async def process_set_status_ready(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split(':')[1])

    # Обновляем статус пользователя на "готово"
    product_manager = ProductManager(INSPIRA_DB)
    status_update_product_status = product_manager.update_product_status(user_id, "DONE")

    if status_update_product_status:
        message_for_admin = f'{ADMIN_PREFIX_TEXT}<b>ГОТОВО</b>\n<i>Статус изделия для {user_id} задан</i>'
        await bot.send_message(
            user_id,
            f"<b>Уважаемый гость!</b>\n"
            f"Ваше изделие готово, можете забирать!",
            parse_mode='HTML'
        )
    else:
        message_for_admin = f'<b>ОШИБКА</b>\nСтатус изделия для {user_id} <b>НЕ ЗАДАН</b>'

    await bot.send_message(
        admin_user_id,
        message_for_admin,
        parse_mode='HTML'
    )


@dp.callback_query_handler(lambda c: c.data.startswith('product_has_been_received:'))
async def process_set_status_ready(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split(':')[1])

    # Обновляем статус пользователя на "готово"
    product_manager = ProductManager(INSPIRA_DB)
    status_update_product_status = product_manager.update_product_status(user_id, "RECEIVED")

    await bot.send_message(
        admin_user_id,
        f"{ADMIN_PREFIX_TEXT}Пользователь {user_id} подтвердил получение", parse_mode='HTML'
    )

    if status_update_product_status:
        message_for_user = (f'<b>Расскажите о своих впечатлениях!</b>\n\n'
                            f'Уделите совсем немного времени, чтобы рассказать о них в этом опросе:\n'
                            f'<a href="https://google.com">тут крч ссылка будет</a>')
    else:
        message_for_user = f'<b>Изделие еще не готово :(</b>\n\nБот уведомит как только оно будет готово!'

    await bot.send_message(
        callback_query.from_user.id, message_for_user, parse_mode='HTML'
    )


@dp.message_handler(lambda message: message.text == '/GROUPS/')
async def show_all_groups(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)

        product_manager = ProductManager(INSPIRA_DB)
        list_users_data = product_manager.get_all_groups()

        unique_groups = set(item[4] for item in list_users_data)
        unique_groups_list = list(unique_groups)

        markup = InlineKeyboardMarkup()
        for group in unique_groups_list:
            button = InlineKeyboardButton(f"ГРУППА {group}", callback_data=f"list_all_users_by_group:{group}")
            markup.add(button)

        _sent_message = await bot.send_message(
            admin_user_id,
            f"{ADMIN_PREFIX_TEXT}"
            f"СПИСОК ВСЕХ ДОСТУПНЫХ ГРУПП",
            reply_markup=markup
        )
        await drop_admin_message(message, _sent_message)


@dp.callback_query_handler(lambda c: c.data.startswith('list_all_users_by_group:'))
async def list_all_users_by_group(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == admin_user_id:
        group_number = callback_query.data.split(':')[1]

        product_manager = ProductManager(INSPIRA_DB)
        list_users_from_group = product_manager.find_all_users_from_group(group_number)

        markup = InlineKeyboardMarkup()
        for user_id in list_users_from_group:
            button = InlineKeyboardButton(f"Гость {user_id}", callback_data=f"user_card:{user_id}")
            markup.add(button)

        _sent_message = await bot.send_message(
            admin_user_id,
            f"{ADMIN_PREFIX_TEXT}"
            f"ГОСТИ ИЗ ГРУППЫ <b>{group_number}</b>",
            reply_markup=markup,
            parse_mode='HTML'
        )


@dp.callback_query_handler(lambda c: c.data.startswith('user_card:'))
async def user_card(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == admin_user_id:
        user_id = int(callback_query.data.split(':')[1])

        product_manager = ProductManager(INSPIRA_DB)
        card_user = product_manager.get_user_card(user_id)

        markup = InlineKeyboardMarkup()

        if card_user['product_status'] == 'WAIT':
            ready_button = InlineKeyboardButton(
                f"ПРИВЕСТИ ИЗДЕЛИЕ К РАБОТЕ", callback_data=f"bring_the_product_to_work:{user_id}")
            markup.add(ready_button)

        elif card_user['product_status'] == 'WORK':
            ready_button = InlineKeyboardButton(
                f"ПРИВЕСТИ ИЗДЕЛИЕ К ПОЛУЧЕНИЮ", callback_data=f"set_status_ready:{user_id}")
            markup.add(ready_button)

        _sent_message = await bot.send_message(
            admin_user_id,
            f"Карточка пользователя <b>{user_id}</b>\n\n"
            f"Номер изделия: <b>{card_user['product_id']}</b>\n"
            f"Статус изделия: <b>{PRODUCT_STATUSES[card_user['product_status']]}</b>\n"
            f"Группа: <b>{card_user['group_id']}</b>\n\n"
            f"<i>Статус обновлен <b>{card_user['update_product_status']}</b></i>",
            parse_mode='HTML',
            reply_markup=markup
        )


@dp.message_handler(lambda message: message.text == '/LOGS/')
async def show_logs(message: types.Message):
    if message.from_user.id == admin_user_id:
        wait_message = await message.answer("[~LOADING~]")
        await construction_to_delete_messages(message)

        logs = await read_logs()
        max_logs_to_show = 20

        def format_log_entry(log_entry, prev_log_entry=None):
            log_time = datetime.datetime.strptime(log_entry[FIELDS_LOG[1]], "%H:%M:%S-%d.%m.%Y")
            log_text = (
                f"Time: {log_entry[FIELDS_LOG[1]]}\n"
                f"Cause: {log_entry[FIELDS_LOG[3]]}\n"
                f"Status: {log_entry[FIELDS_LOG[2]]}"
            )
            if prev_log_entry:
                prev_log_time = datetime.datetime.strptime(prev_log_entry[FIELDS_LOG[1]], "%H:%M:%S-%d.%m.%Y")
                time_diff = round((log_time - prev_log_time).total_seconds())
                log_text += f"      ⚠️  {time_diff} sec"
            return log_text

        if len(logs) <= max_logs_to_show:
            logs_text = "\n\n".join([format_log_entry(log) for log in logs])
        else:
            last_logs = logs[-max_logs_to_show:]
            logs_text = "\n\n".join(
                [format_log_entry(log, prev_log) for log, prev_log in zip(last_logs[1:], last_logs[:-1])])
        if logs_text:
            sent_message = await message.answer("// LAST LOGS:\n\n" + logs_text)
        else:
            sent_message = await message.answer("// EMPTY //")

        await wait_message.delete()
        await drop_admin_message(message, sent_message)
    else:
        write_log('TRY CHECK LOGS', 'WARNING')
        await message.answer("$^@!($@&() DB_ERR")


@dp.message_handler(lambda message: message.text == '/USERS/')
async def show_all_users(message: types.Message):
    if message.from_user.id == admin_user_id:
        wait_message = await message.answer("➜ LOADING DB... ///")
        await construction_to_delete_messages(message)

        user_manager = UserManager(INSPIRA_DB)
        all_users = user_manager.read_users_from_db()

        users_from_db = '➜ LAST USERS ➜\n\n'
        users_from_db_count = 0

        cnt_users = len(all_users)

        date_format = "%H:%M %d-%m-%Y"
        sorted_users = reversed(sorted(all_users, key=lambda x: datetime.datetime.strptime(x[5], date_format)))

        for user in sorted_users:
            id_in_db = user[0]
            user_id = user[1]
            firstname = user[2]
            username = user[4]
            date = user[5]

            users_from_db += f"[{id_in_db}]: ({str(date).split(' ')[0]}) {firstname}\n{user_id}\n"
            users_from_db_count += 1

            if users_from_db_count >= 20:
                users_from_db += f'... и еще {cnt_users - 20}\n'
                users_from_db += f'[ADMIN] ' \
                                 f'{sorted(all_users, key=lambda x: datetime.datetime.strptime(x[5], date_format))[0][1]}'
                break

        users_from_db += f"\n\n<b>➜ TOTAL {cnt_users}</b>"

        await wait_message.delete()
        sent_message = await message.answer(users_from_db, parse_mode="HTML")
        await drop_admin_message(message, sent_message)


@dp.message_handler(lambda message: message.text == '/PC/')
async def monitor_process(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)
        try:
            from server_info import MachineResources

            machine_resources = MachineResources()
            sent_message = await message.answer(machine_resources.get_all_info())

            await drop_admin_message(message, sent_message)
        except ModuleNotFoundError as e:
            await message.answer("Ошибка импортирования модуля", e)


@dp.message_handler(lambda message: message.text == '/OTHER/')
async def other_commands(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)
        commands = '// COMMANDS //\n\n'
        commands += '/black_list - (c)\n' \
                    '/block - (c, i)\n' \
                    '/unblock - (c, i)\n' \
                    '/sms - (c, i, m)\n' \
                    '/sms_video - (c, video, i)' \
                    '/stop_all - (c)\n\n' \
                    '/referral - (c)\n' \
                    '/c - (c)\n' \
                    '/i - (c, i)\n' \
                    '/l - (c, i)\n\n' \
                    '/price_p - (c, i, p)\n' \
                    '/address_p - (c, i, a)\n\n' \
                    '/all - (c, m)\n' \
                    '/rates - (c)\n\n' \
                    '/rate_user - (c, id) ' \
                    '/rate_all - (c)\n\n'
        sent_message = await message.answer(commands)
        await drop_admin_message(message, sent_message)


limited_users_manager = LimitedUsersManager(INSPIRA_DB)


@dp.message_handler(commands=['limited_users'])
async def blacklist_cat_users(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)

        blocked_users = await limited_users_manager.fetch_all_users()
        sent_message = await message.answer(blocked_users)

        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['block'])
async def block_user(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)
        try:
            answer = await limited_users_manager.block_user(message.text)
            sent_message = await message.reply(f"<b>{answer}</b>", parse_mode='HTML')
        except sqlite3.IntegrityError:
            sent_message = await message.reply(f"<b>ALREADY BLOCKED 🟧</b>", parse_mode='HTML')
        except Exception as e:
            sent_message = await message.reply("/// ERROR:", e)
        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['unblock'])
async def unblock_user(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)
        try:
            answer = await limited_users_manager.unblock_user(message.text)
            sent_message = await message.reply(f"<b>{answer}</b>", parse_mode='HTML')
        except Exception as e:
            sent_message = await message.reply("/// ERROR:", e)
        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['i'])
async def req_in_db(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)

        try:
            _user_id = int(message.text.split()[1])
        except ValueError:
            _user_id = message.text.split()[1]

        user_manager = UserManager(INSPIRA_DB)
        find_users = user_manager.find_users_in_db(_user_id)

        try:
            status_user_in_bot = await limited_users_manager.check_user_for_block(_user_id)
        except OverflowError as overflow:
            await message.answer(f"➜ ERROR ➜\n\n{overflow}")
            return

        if status_user_in_bot:
            text_status_user_in_bot = '➜ (DIRTY ❌)'
        else:
            text_status_user_in_bot = '➜ (CLEAR ✅)'

        if find_users:
            sent_message = await message.answer(f"➜ USER exist ➜\n\n{find_users}\n\n{text_status_user_in_bot}")
        else:
            sent_message = await message.answer(f"➜ USER not exist ❌")

        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['l'])
async def req_in_db(message: types.Message):
    if message.from_user.id == admin_user_id:
        await construction_to_delete_messages(message)

        _user_id = int(message.text.split()[1])
        logs = reversed(await read_logs())

        cnt = 0
        limit = 20
        logs_text = []
        for item in logs:
            numbers = re.findall(r'\d+', item['status'])
            if str(_user_id) in numbers:
                if 'PARSING for ' not in item['status']:
                    cnt += 1
                    logs_text.append(item)
                    if cnt == limit:
                        break
        log_mes = f"// LAST LOGS for {_user_id}\n\n"
        if logs_text:
            last_logs = reversed(logs_text)

            for i in last_logs:
                log_mes += f"Date: {i['date']}\n" \
                           f"Status: {i['status']}\n" \
                           f"Cause: {i['cause']}"
                log_mes += '\n\n'
            sent_message = await message.answer(log_mes)
        else:
            sent_message = await message.answer("// EMPTY //")

        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['del'])
async def req_in_db(message: types.Message):
    if message.from_user.id == admin_user_id:
        try:
            _user_id = int(message.text.split()[1])

            user_manager = UserManager(INSPIRA_DB)

            try:
                user_manager.drop_user_from_db(_user_id)
                await message.answer("<b>DROP USER: OK ✅</b>", parse_mode='HTML')
            except Exception as e:
                await message.answer(f"<b>DROP USER: ERROR ❌</b>\n\n{e}", parse_mode='HTML')

        except Exception:
            await message.reply("Неверно переданы аргументы.")


@dp.message_handler(commands=['sms'])
async def send_html_message(message: types.Message):
    """
        Отправка сообщения пользователю по user_id, с HTML-форматированием
    """
    if message.from_user.id == admin_user_id:
        try:
            adv_text = len(message.text.split())
            if adv_text > 2:
                _message = ' '.join(message.text.split()[2:])
            else:
                _message = message.text.split()[2]

            _message = _message.replace("\\n", "\n")

            try:
                await bot.send_message(chat_id=message.text.split()[1], text=_message, parse_mode="HTML")
                await message.answer("<b>ДОСТАВЛЕНО ✅</b>", parse_mode='HTML')
            except Exception as e:
                print(e)
                await message.answer("<b>НЕ УДАЛОСЬ ❌</b>", parse_mode='HTML')
        except Exception:
            await message.reply("Неверно переданы аргументы.")


@dp.message_handler(commands=['sms_video'])
async def send_html_message(message: types.Message):
    """
        Отправка сообщения пользователю по user_id, с HTML-форматированием
    """
    if message.from_user.id == admin_user_id:
        try:
            vid_path = message.text.split(' ')[1]
            chat_id = message.text.split(' ')[2]

            try:
                with open(vid_path, 'rb') as gif:
                    await bot.send_animation(chat_id=chat_id, animation=gif)
                await message.answer("<b>ДОСТАВЛЕНО ✅</b>", parse_mode='HTML')
            except Exception as e:
                print(e)
                await message.answer("<b>НЕ УДАЛОСЬ ❌</b>", parse_mode='HTML')
        except Exception:
            await message.reply("Неверно переданы аргументы.")


@dp.message_handler(commands=['all'])
async def sent_message_to_user(message: types.Message):
    if message.from_user.id == admin_user_id:
        keyboard = types.ReplyKeyboardMarkup(keyboard=ADMIN_PANEL_BUTTONS, resize_keyboard=True)

        # try:
        split_cnt = len(message.text.split())
        if split_cnt > 2:
            _message = ' '.join(message.text.split()[1:])
        else:
            _message = message.text.split()[1]
        _message = _message.replace("\\n", "\n")

        user_manager = UserManager(INSPIRA_DB)
        users_load = user_manager.read_users_from_db()

        cnt_users = 0
        cnt_er = 0
        count = 0

        import time

        sent_mes = await bot.send_message(admin_user_id, "➜ <b>SENDING STREAM MESSAGES</b> ... [wait]", parse_mode='HTML')
        start_time = time.time()

        for row in users_load:
            count += 1
            _user_id = row[1]

            try:
                status_user_in_bot = await limited_users_manager.check_user_for_block(_user_id)

                if (cnt_users % 15 == 0) and (cnt_users != 0):
                    print('sleep 5:', cnt_users, len(users_load), count)
                    await asyncio.sleep(5)
                else:
                    print('sleep 0.25:', cnt_users, len(users_load), count)
                    await asyncio.sleep(.25)

                if status_user_in_bot:
                    print('pass user', count)
                else:
                    await bot.send_message(chat_id=_user_id, text=_message, parse_mode="HTML")
                    cnt_users += 1

            except Exception:
                cnt_er += 1

        end_time = time.time()
        execution_time = round(end_time - start_time)

        hours = int(execution_time // 3600)
        minutes = int((execution_time % 3600) // 60)
        seconds = int(execution_time % 60)
        final_people_text_execution_time = f'{hours} h, {minutes} m, {seconds} s'

        await sent_mes.delete()
        await bot.send_message(
            admin_user_id, f"➜ DONE {cnt_users}\n➜ NOT COMPLETED {cnt_er}\n\n"
                           f"➜ TIMING - {final_people_text_execution_time}",
            reply_markup=keyboard)


@dp.message_handler(commands=['reboot'])
async def reboot_server(message: types.Message):
    if message.from_user.id == admin_user_id:
        await message.reply("➜ REBOOT in 5 sec... ➜")
        await asyncio.sleep(5)
        await ServerManager().emergency_reboot()
    else:
        write_log(f"USER {message.from_user.id} in reboot_server", "WARNING")
        await message.reply("& Ты шо гад, попутал?")


class ServerManager:
    @staticmethod
    def __reboot_server():
        write_log("reboot_server", "OK")
        os.execl(sys.executable, sys.executable, *sys.argv)

    async def emergency_reboot(self):
        print("emergency_reboot: start")
        write_log("emergency_reboot", "START")
        try:
            write_log(f"emergency_reboot", "OK")
        except Exception as e:
            write_log(f"emergency_reboot: {e}", "ERROR")

        self.__reboot_server()


# prices
PRICE = types.LabeledPrice(label="Подписка на 1 месяц", amount=100*100)


@dp.message_handler(commands=['buy'])
async def buy(message: types.Message):
    if "TEST" in PAYMENTS_TOKEN:
        await bot.send_message(message.chat.id, "!Тестовый платеж!")
    await bot.send_invoice(
        message.chat.id,
        title="Расширенная подписка",
        description="Увеличенный лимит, приоритетная поддержка, кастомизация",
        provider_token=PAYMENTS_TOKEN,
        currency="rub",
        photo_url="https://i.pinimg.com/736x/d3/07/2b/d3072b58b5aeb0e852ff1d12c2ec2b5a.jpg",
        is_flexible=False,
        prices=[PRICE],
        start_parameter="one-month-subscription",
        payload="test-invoice-payload")


# @dp.message_handler(commands=['buy_u'])
# async def buy(message: types.Message):

# ==========================================================================


# ==========================================================================
# --------------------- СЕРВЕРНАЯ ЧАСТЬ: ЛОГИРОВАНИЕ -----------------------
def write_log(cause, status):
    """ Логирование """
    def get_time_now():      # Получение и форматирование текущего времени
        hms = datetime.datetime.today()
        time_format = f"{hms.hour}:{hms.minute}:{hms.second}"
        date_format = f"{hms.day}.{hms.month}.{hms.year}"
        return f"{time_format}-{date_format}"

    if os.path.exists(FILE_LOG) is False:
        with open(FILE_LOG, mode="a", encoding='utf-8') as data:
            logs_writer = DictWriter(data, fieldnames=FIELDS_LOG, delimiter=';')
            logs_writer.writeheader()
            data.close()

    log_data = open(FILE_LOG, mode="a", encoding='utf-8')
    log_writer = DictWriter(log_data, fieldnames=FIELDS_LOG, delimiter=';')
    log_writer.writerow({
        FIELDS_LOG[0]: __version__,     # Запись версии
        FIELDS_LOG[1]: get_time_now(),  # Запись даты и времени
        FIELDS_LOG[2]: status,          # Запись причины
        FIELDS_LOG[3]: cause            # Запись статуса
    })
    log_data.close()


@timing_decorator
async def read_logs():
    if os.path.exists(FILE_LOG):
        logs_data = []
        with open(FILE_LOG, mode="r", encoding='utf-8') as data:
            logs_reader = DictReader(data, fieldnames=FIELDS_LOG, delimiter=';')
            next(logs_reader)
            for row in logs_reader:
                logs_data.append(row)
            data.close()
        return logs_data
    else:
        return []
# ==========================================================================


async def on_startup(dp):
    os.system('clear')
    print('==================== BOT INSPIRA START ========================')
    print(
    """
    INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA
    INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA
    INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA INSPIRA
    """
    )
    print(f'===== DEBUG: {DEBUG} =============================================')
    print(f'===== INSPIRA: {__version__}  =======================================')


if __name__ == '__main__':
    try:
        dp.register_message_handler(admin_panel, commands=["ins2133"])
        executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

    except aiogram.utils.exceptions.TelegramAPIError as aiogram_critical_error:
        print("\n\n\n* !!! CRITICAL !!! * --- aiogram ---", aiogram_critical_error, "\n\n\n")
        write_log(aiogram_critical_error, "CRITICAL")
        ServerManager().emergency_reboot()

    except aiohttp.client_exceptions.ServerDisconnectedError as aiohttp_critical_error:
        print("\n\n\n* !!! CRITICAL !!! * --- aiohttp ---", aiohttp_critical_error, "\n\n\n")
        write_log(aiohttp_critical_error, "CRITICAL")
        ServerManager().emergency_reboot()

    except Exception as e:
        write_log(f"Exception: {e}", "CRITICAL")
        ServerManager().emergency_reboot()
