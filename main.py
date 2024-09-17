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


from server_info import timing_decorator
from database_manager import *
from tracer import TracerManager, TRACER_FILE


__version__ = '0.0.2.0'
DEBUG = True


try:
    with open('config.json') as config_file:
        _config = json.load(config_file)
    exhibit = str(_config["telegram_beta_token"])
    superuser_id = _config["superuser_id"]
    PAYMENTS_TOKEN = _config["payment_token"]
except Exception as e:
    exhibit = None
    print("ОШИБКА при ЧТЕНИИ токена ТЕЛЕГРАМ", e)


bot = Bot(token=exhibit)
dp = Dispatcher(bot, storage=MemoryStorage())


# ================ БАЗА ДАННЫХ И ТАБЛИЦЫ ================
db_manager = DataBaseManager(INSPIRA_DB)
db_manager.create_table(USERS_TABLE_NAME, FIELDS_FOR_USERS)
db_manager.create_table(PRODUCTS_TABLE_NAME, FIELDS_FOR_PRODUCTS)
db_manager.create_table(REFERRALS_TABLE_NAME, FIELDS_FOR_REFERRALS)
db_manager.create_table(LIMITED_USERS_TABLE_NAME, FIELDS_FOR_LIMITED_USERS)
db_manager.create_table(ADMINS_TABLE_NAME, FIELDS_FOR_ADMINS)

# ============== ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ ===========================
tracer_l = TracerManager(TRACER_FILE)

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


class Administrators:
    def __init__(self, admin_list: list):
        self.admin_list = admin_list

    async def sending_messages_to_admins(self, message: str, parse_mode='HTML', markup=None):
        for _admin_user_id in self.admin_list:
            await bot.send_message(_admin_user_id, message, parse_mode=parse_mode, reply_markup=markup)

    def get_list_of_admins(self) -> list:
        return self.admin_list


# Инициализация администраторов
administrators = Administrators(admin_list=[456666281]) # 1243722606, 506667650


@timing_decorator
async def check_ban_users(user_id):
    # -------------------БАН ЮЗЕРОВ --------------

    check = await check_temporary_block(user_id)
    if check:
        return True

    result = await limited_users_manager.check_user_for_block(user_id)

    if result:
        if user_id not in notify_banned_users:
            await administrators.sending_messages_to_admins(f"⚠ {user_id} VERSUCHT RAUS ZU KOMMEN\n\n")
            await bot.send_message(
                user_id, f"К сожалению, не можем допустить Вас к использованию бота :(\n\n"
                         f"(T_T)", parse_mode='HTML'
            )

            notify_banned_users.append(user_id)
            tracer_l.tracer_charge(
                "ADMIN", user_id, "check_ban_users", "VERSUCHT RAUS ZU KOMMEN")
        return True


async def block_user_temporarily(user_id):
    temporarily_blocked_users[user_id] = datetime.datetime.now() + datetime.timedelta(minutes=30)
    await bot.send_message(
        user_id,
        f"К сожалению, не можем допустить Вас к использованию бота :(\n\n{temporarily_blocked_users[user_id]}", parse_mode='HTML')


async def check_temporary_block(user_id):
    if user_id in temporarily_blocked_users:
        if datetime.datetime.now() > temporarily_blocked_users[user_id]:
            del temporarily_blocked_users[user_id]
            return False
        else:
            tracer_l.tracer_charge(
                'ADMIN', user_id, check_temporary_block.__name__, "user will temp banned")
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
            await administrators.sending_messages_to_admins(f"ЛИКВИДИРОВАН ❌")
            tracer_l.tracer_charge(
                'ADMIN', user_id, ban_request_restrictions.__name__, "user will permanent banned")

        if await check_temporary_block(user_id) is False:
            await block_user_temporarily(user_id)
            user_messages[user_id] = []


@timing_decorator
async def check_user_data(message):
    user_id = message.from_user.id
    first_name = message.chat.first_name
    last_name = message.chat.last_name

    user_manager = UserManager(INSPIRA_DB)
    result = user_manager.check_user_in_database(user_id)

    if not result:
        _time_now = datetime.datetime.now().strftime('%H:%M %d-%m-%Y')
        user_data = {
            'user_id': message.from_user.id, 'fullname': message.chat.first_name,
            'date_register': _time_now, 'user_status': True,
            'user_status_date_upd': _time_now
        }
        user_manager.add_record('users', user_data)

        product_user_data = {
            'product_id': None, 'status': None, 'user_id': message.from_user.id, 'group_number': None,
            'status_update_date': _time_now
        }

        _db_manager = ProductManager(INSPIRA_DB)
        _db_manager.add_record('products', product_user_data)

        # Кнопка для администратора
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton("ДОБАВИТЬ ГОСТЯ В ГРУППУ", callback_data=f"fill_guest_card:{user_id}")
        markup.add(button)

        await administrators.sending_messages_to_admins(
            f"⚠ НОВЫЙ ГОСТЬ ⚠\n{first_name} {last_name} ({user_id})", markup=markup)

        tracer_l.tracer_charge(
            'ADMIN', message.from_user.id, check_user_data.__name__, "new user")

    return result


# ============================================================================
# ------------------------- ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ -------------------------
@dp.message_handler(text='Запуск')
@dp.message_handler(text='Старт')
@dp.message_handler(text='Начать')
@dp.message_handler(commands=['start'])
async def start_message(message: types.Message):
    if await check_ban_users(message.from_user.id) is not True:
        tracer_l.tracer_charge(
            'INFO', message.from_user.id, start_message.__name__, "user launched bot")

        wait_message = await message.answer(
            "<b>➔ INSPIRA</b>\n"
            "Creative workshop\n\n"
            "<b>↧ DESIGN by </b>KOZAK\n",
            parse_mode='HTML'
        )
        await check_user_data(message)

        check_for_ref = message.text.split(' ')

        if len(check_for_ref) > 1:
            check_for_ref = check_for_ref[1]
            ref_manager = ReferralArrival(INSPIRA_DB)
            ref_manager.check_user_ref(message.from_user.id, check_for_ref)
            print("ID ARRIVAL:", check_for_ref, message.from_user.id)

        await asyncio.sleep(.5)

        product_manager = ProductManager(INSPIRA_DB)
        product_id_by_user = product_manager.get_product_id(user_id=message.from_user.id)

        if message.from_user.id in administrators.get_list_of_admins():
            kb = [
                [
                    types.KeyboardButton(text="/ADMIN/"),
                ]
            ]
            tracer_l.tracer_charge(
                'INFO', message.from_user.id, '/start', "display admin button")
        else:
            if product_id_by_user is None:
                kb = [[types.KeyboardButton(text="Заполнить контактную информацию")]]
                tracer_l.tracer_charge(
                    'INFO', message.from_user.id, '/start', "user: not logged in")
            else:
                kb = [[types.KeyboardButton(text="Узнать статус изделия")]]
                tracer_l.tracer_charge(
                    'INFO', message.from_user.id, '/start', "user: logged in")

        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

        try:
            await bot.send_photo(
                message.from_user.id, photo=InputFile('media/img/menu.png', filename='start_message.png'),
                reply_markup=keyboard, parse_mode='HTML',
                caption=f'<b>INSPIRA – искусство живет здесь.</b>\n\n'
                        f'Привет! Это Бот Inspira - тут ты можешь записаться на мастер-класс по гончарному делу, '
                        f'а также узнать о готовности твоего изделия')
            tracer_l.tracer_charge(
                'INFO', message.from_user.id, '/start', "user received start message")
        except Exception as error:
            tracer_l.tracer_charge(
                'ERROR', message.from_user.id, '/start',
                "user failed received start message", f"{error}")
        await wait_message.delete()


@dp.message_handler(lambda message: message.text == 'Заполнить контактную информацию')
async def get_contact_info(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    phone_button = types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)
    keyboard.add(phone_button)
    tracer_l.tracer_charge(
        'INFO', message.from_user.id, get_contact_info.__name__, "offer to send a contact")
    await message.answer("Пожалуйста, отправьте свой номер телефона:", reply_markup=keyboard)


@dp.message_handler(content_types=types.ContentType.CONTACT)
async def contact_handler(message: types.Message):
    user_id = message.from_user.id
    phone = message.contact.phone_number

    try:
        user_manager = UserManager(INSPIRA_DB)
        user_manager.update_contact_info(user_id=user_id, phone=phone)
        tracer_l.tracer_charge(
            'INFO', message.from_user.id, contact_handler.__name__, "offer to send a contact")
    except Exception as db_error:
        tracer_l.tracer_charge(
            'CRITICAL', message.from_user.id, contact_handler.__name__,
            "error saving the contact in database", f"{db_error}")

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

    await message.answer(f"Успешно! ✅", reply_markup=keyboard)


@dp.message_handler(commands=['help'])
async def help_user(message: types.Message):
    # =========== ПРОВЕРКА ДОПУСКА ПОЛЬЗОВАТЕЛЯ ================
    if await check_ban_users(message.from_user.id) is not True:
        tracer_l.tracer_charge(
            'INFO', message.from_user.id, help_user.__name__, "user in help")

        url_kb = InlineKeyboardMarkup(row_width=2)
        url_help = InlineKeyboardButton(text='Поддержка', url='https://google.com')
        url_link = InlineKeyboardButton(text='Наш сайт', url='https://google.com')
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
    tracer_l.tracer_charge(
        'INFO', message.from_user.id, product_status.__name__, "user check status of product")

    user_manager = UserManager(INSPIRA_DB)
    phone_from_user = user_manager.get_phone(message.from_user.id)

    if phone_from_user is None:
        kb = [
            [
                types.KeyboardButton(text="Заполнить контактную информацию"),
            ],
            [
                types.KeyboardButton(text="Больше"),
                types.KeyboardButton(text="Помощь")
            ]
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

        await bot.send_message(message.from_user.id,
                               "<b>Упс..</b>\n"
                               "Вы не авторизованы\n\n"
                               "<i>Подтвердите свой аккаунт, отправив номер телефона</i>",
                               reply_markup=keyboard, parse_mode='HTML')
        tracer_l.tracer_charge(
            'INFO', message.from_user.id, product_status.__name__, "user: not logged in")
    else:
        _db_manager = ProductManager(INSPIRA_DB)
        _status_product = _db_manager.get_product_status(message.from_user.id)

        if _status_product == 'WORK':
            await bot.send_message(
                message.from_user.id,
                'В РАБОТЕ ⌛\n\n<i>Вам придет уведомление, как только Ваше изделие будет готово.</i>',
                parse_mode='HTML'
            )

        elif _status_product == 'DONE':
            markup = InlineKeyboardMarkup()
            ready_button = InlineKeyboardButton(
                "ИЗДЕЛИЕ ПОЛУЧИЛ",
                callback_data=f"product_has_been_received:{message.from_user.id}")
            markup.add(ready_button)
            await bot.send_message(
                message.from_user.id, '<b>ГОТОВО ✅</b>\n\nМожете забрать свое творение!', reply_markup=markup,
                parse_mode='HTML'
            )

        elif _status_product == 'RECEIVED':
            await bot.send_message(
                message.from_user.id, '<b>ИЗДЕЛИЕ НА РУКАХ</b>\n\nПриходите к нам ещё!',
                parse_mode='HTML'
            )

        elif _status_product == 'WAIT':
            await bot.send_message(
                message.from_user.id,
                '<b>ИЗДЕЛИЕ В ОЧЕРЕДИ</b>\n\nВам придет уведомление, когда Ваше изделие пойдет в работу.',
                parse_mode='HTML'
            )

        else:
            await bot.send_message(
                message.from_user.id,
                '<b>Статус не определен :(</b>\n\nКак только Ваше изделие начнет готовиться, Вам придет уведомление',
                parse_mode='HTML'
            )

        tracer_l.tracer_charge(
            'INFO', message.from_user.id, product_status.__name__, f"product status: {_status_product}")


def standard_datetime_format():
    return f"\n[{datetime.datetime.now().strftime('%H:%M:%S - %d.%m')}]"


def format_number(num):
    return '{0:,}'.format(num).replace(",", " ")


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
            types.KeyboardButton(text="/COMMANDS/"),
            types.KeyboardButton(text="/3/")
        ],
        [
            types.KeyboardButton(text="/USERS/"),
            types.KeyboardButton(text="/LOGS/"),
            types.KeyboardButton(text="/PC/")
        ]
    ]


@dp.message_handler(lambda message: message.text == 'ins2133')
@dp.message_handler(lambda message: message.text == '/ADMIN/')
@dp.message_handler(commands=['ins2133'])
async def admin_panel(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
        keyboard = types.ReplyKeyboardMarkup(keyboard=ADMIN_PANEL_BUTTONS, resize_keyboard=True)
        await message.reply(
            "[ INSPIRA • Admin Panel ]\n\n"
            "<b>Панель администратора</b>\n"
            "<i>Здесь Вы можете:\n"
            "• Назначать статусы изделий\n"
            "• Просматривать информацию о гостях и их действиях</i>\n"
            "• Блокировать гостей, которые неправомерно используют бот\n"
            "• Просматривать потребление системных ресурсов", reply_markup=keyboard, parse_mode='HTML')
        tracer_l.tracer_charge(
            'ADMIN', message.from_user.id, admin_panel.__name__, "admin in control panel")


class FormGroupProduct(StatesGroup):
    group = State()
    product_id = State()
    user_id = 0


# @dp.message_handler(lambda message: "add_to_group" in message.text)
@dp.callback_query_handler(lambda c: c.data.startswith('fill_guest_card:'))
async def start_form(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = int(callback_query.data.split(':')[1])

    tracer_l.tracer_charge(
        'ADMIN', callback_query.from_user.id, start_form.__name__,
        f"admin set group number for {user_id}")

    await callback_query.message.answer(f"Введите номер группы для {user_id}")
    async with state.proxy() as data:
        data['user_id'] = user_id
    await FormGroupProduct.group.set()


@dp.message_handler(state=FormGroupProduct.group)
async def process_group(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['group'] = message.text
    await message.answer(f"Теперь введите номер изделия для {data['user_id']}")
    await FormGroupProduct.product_id.set()


@dp.message_handler(state=FormGroupProduct.product_id)
async def process_product_number(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['product_id'] = message.text
        target_user_id = data['user_id']

    tracer_l.tracer_charge(
        'ADMIN', message.from_user.id, process_product_number.__name__,
        f"admin filled card for {target_user_id}")

    markup = InlineKeyboardMarkup()
    ready_button = InlineKeyboardButton(
        "ПРИВЕСТИ ИЗДЕЛИЕ В РАБОТУ", callback_data=f"bring_the_product_to_work:{target_user_id}")
    markup.add(ready_button)

    try:
        _db_manager = ProductManager(INSPIRA_DB)
        _db_manager.update_user_group(target_user_id, data['group'], "WAIT")
        _db_manager.update_product_id(target_user_id, data['product_id'])

        await message.answer(
            f"<b>Гость {target_user_id} добавлен</b>\n"
            f"Номер группы  – {data['group']}\n"
            f"Номер изделия – {data['product_id']}",
            reply_markup=markup, parse_mode='HTML'
        )

        tracer_l.tracer_charge(
            'ADMIN', message.from_user.id, process_product_number.__name__,
            f"user {target_user_id} has been added")

        await state.finish()

    except Exception as er:
        tracer_l.tracer_charge(
            'ERROR', message.from_user.id, process_product_number.__name__,
            f"FAIL while filled user card {target_user_id}", f"{e}")

        await message.answer(f"Ошибка! Попробуйте заново\n\n{er}")


@dp.callback_query_handler(lambda c: c.data.startswith('bring_the_product_to_work:'))
async def bring_the_product_to_work(callback_query: types.CallbackQuery):
    if callback_query.from_user.id in administrators.get_list_of_admins():
        user_id = int(callback_query.data.split(':')[1])

        try:
            product_manager = ProductManager(INSPIRA_DB)
            product_manager.update_product_status(user_id, "WORK")
            _user_card = product_manager.get_user_card(user_id)

            await administrators.sending_messages_to_admins(
                f"{ADMIN_PREFIX_TEXT}"
                f"<b>ПРИНЯТО В РАБОТУ</b>\n\n"
                f"• Статус изделия: <b>{PRODUCT_STATUSES[_user_card['product_status']]}</b>\n"
                f"• Номер группы: <b>{_user_card['group_id']}</b>\n\n"
                f"<i>Обновлено {_user_card['update_product_status']}</i>"
            )

            await bot.send_message(
                user_id,
                f"{USER_PREFIX_TEXT}"
                f"Ваше изделие принято в работу!\n\n"
                f"<i>Вам придёт уведомление о готовности</i>",
                parse_mode='HTML'
            )
            tracer_l.tracer_charge(
                'ADMIN', callback_query.from_user.id, bring_the_product_to_work.__name__,
                f"product status for {user_id}: in process")
        except Exception as critical:
            tracer_l.tracer_charge(
                'ERROR', callback_query.from_user.id, bring_the_product_to_work.__name__,
                f"error in process accepted for work", f"{critical}")
    else:
        tracer_l.tracer_charge(
            'WARNING', callback_query.from_user.id, bring_the_product_to_work.__name__,
            f"user try to check this function")


@dp.callback_query_handler(lambda c: c.data.startswith('set_status_ready:'))
async def process_set_status_ready(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split(':')[1])

    product_manager = ProductManager(INSPIRA_DB)
    status_update_product_status = product_manager.update_product_status(user_id, "DONE")

    markup = InlineKeyboardMarkup()
    ready_button = InlineKeyboardButton("ИЗДЕЛИЕ ПОЛУЧИЛ", callback_data=f"product_has_been_received:{user_id}")
    markup.add(ready_button)

    if status_update_product_status:
        message_for_admin = f'{ADMIN_PREFIX_TEXT}<b>ГОТОВО</b>\n\n<i>Статус изделия для {user_id}: ГОТОВ</i>'
        await bot.send_message(
            user_id,
            f"{USER_PREFIX_TEXT}"
            f"Ваше изделие готово, можете забирать!\n\n"
            f"<i>Как только получите, пожалуйста, подтвердите получение по кнопке ниже.</i>",
            parse_mode='HTML', reply_markup=markup
        )

        tracer_l.tracer_charge(
            'ADMIN', callback_query.from_user.id, process_set_status_ready.__name__,
            f"product status for {user_id}: done")
    else:
        message_for_admin = f'<b>Ошибочка :(</b>\nСтатус изделия для {user_id} <b>НЕ ЗАДАН</b>'

        tracer_l.tracer_charge(
            'ADMIN', callback_query.from_user.id, process_set_status_ready.__name__,
            f"unknown product status for {user_id}", "product status is not set")

    await administrators.sending_messages_to_admins(message_for_admin)


@dp.callback_query_handler(lambda c: c.data.startswith('product_has_been_received:'))
async def process_product_confirm(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split(':')[1])

    try:
        product_manager = ProductManager(INSPIRA_DB)
        status_update_product_status = product_manager.update_product_status(user_id, "RECEIVED")
        user_group = product_manager.get_group(user_id)
        tracer_l.tracer_charge(
            'INFO', callback_query.from_user.id, process_product_confirm.__name__,
            f"product status for {user_id}: product has been received")
    except Exception as critical:
        tracer_l.tracer_charge(
            'CRITICAL', callback_query.from_user.id, process_product_confirm.__name__,
            f"critical error while update status in database {user_id}", critical)
        return

    await administrators.sending_messages_to_admins(
        f"{ADMIN_PREFIX_TEXT}Гость {user_id} из группы {user_group} подтвердил получение ✅")

    if status_update_product_status:
        message_for_user = (f'<b>Расскажите о своих впечатлениях!</b>\n\n'
                            f'Уделите совсем немного времени, чтобы рассказать о своих впечатлениях в этом опросе:\n'
                            f'<a href="https://google.com">тут крч ссылка будет</a>')
        try:
            await bot.send_message(callback_query.from_user.id, message_for_user, parse_mode='HTML')
            tracer_l.tracer_charge(
                'INFO', callback_query.from_user.id, process_product_confirm.__name__,
                f"finally message will send")
        except Exception as error:
            tracer_l.tracer_charge(
                'WARNING', callback_query.from_user.id, process_product_confirm.__name__,
                f"fail while send finally message", f"{error}")


@dp.message_handler(lambda message: message.text == '/GROUPS/')
async def show_all_groups(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
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
            message.from_user.id,
            f"{ADMIN_PREFIX_TEXT}СПИСОК ВСЕХ ДОСТУПНЫХ ГРУПП", reply_markup=markup, parse_mode='HTML')

        await drop_admin_message(message, _sent_message)


@dp.callback_query_handler(lambda c: c.data.startswith('list_all_users_by_group:'))
async def list_all_users_by_group(callback_query: types.CallbackQuery):
    if callback_query.from_user.id in administrators.get_list_of_admins():
        group_number = callback_query.data.split(':')[1]

        product_manager = ProductManager(INSPIRA_DB)
        list_users_from_group = product_manager.find_all_users_from_group(group_number)

        users_manager = UserManager(INSPIRA_DB)

        markup = InlineKeyboardMarkup()
        for user_id in list_users_from_group:
            user_from_db = users_manager.get_user_contact_info(user_id=user_id)
            button = InlineKeyboardButton(f"Гость {user_from_db}", callback_data=f"user_card:{user_id}")
            markup.add(button)

        _sent_message = await bot.send_message(
            callback_query.from_user.id,
            f"{ADMIN_PREFIX_TEXT}СПИСОК ВСЕХ ДОСТУПНЫХ ГРУПП", reply_markup=markup, parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data.startswith('user_card:'))
async def user_card(callback_query: types.CallbackQuery):
    if callback_query.from_user.id in administrators.get_list_of_admins():
        user_id = int(callback_query.data.split(':')[1])

        product_manager = ProductManager(INSPIRA_DB)
        card_user = product_manager.get_user_card(user_id)

        markup = InlineKeyboardMarkup()

        if card_user['product_status'] == 'WAIT':
            ready_button = InlineKeyboardButton(
                f"ПРИВЕСТИ ИЗДЕЛИЕ В РАБОТУ", callback_data=f"bring_the_product_to_work:{user_id}")
            markup.add(ready_button)

        elif card_user['product_status'] == 'WORK':
            ready_button = InlineKeyboardButton(
                f"ПРИВЕСТИ ИЗДЕЛИЕ К ПОЛУЧЕНИЮ", callback_data=f"set_status_ready:{user_id}")
            markup.add(ready_button)

        try:
            _sent_message = await bot.send_message(
                callback_query.from_user.id,
                f"Карточка пользователя <b>{user_id}</b>\n\n"
                f"Номер изделия: <b>{card_user['product_id']}</b>\n"
                f"Статус изделия: <b>{PRODUCT_STATUSES[card_user['product_status']]}</b>\n"
                f"Группа: <b>{card_user['group_id']}</b>\n\n"
                f"<i>Статус обновлен <b>{card_user['update_product_status']}</b></i>",
                reply_markup=markup, parse_mode='HTML')

        except Exception as e:
            ready_button = InlineKeyboardButton(
                f"ЗАПОЛНИТЬ ЗАНОВО", callback_data=f"fill_guest_card:{user_id}")
            markup.add(ready_button)

            await bot.send_message(
                callback_query.from_user.id,
                f"<b>Ошибочка :(</b>\n\n"
                f"Попробуйте заполнить карточку гостя заново",
                reply_markup=markup, parse_mode='HTML')

            write_log(e, "ERROR")


@dp.message_handler(lambda message: message.text == '/LOGS/')
async def show_logs(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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


@dp.message_handler(commands=['over_right_to_admin'])
async def blacklist_cat_users(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
        await construction_to_delete_messages(message)

        blocked_users = await limited_users_manager.fetch_all_users()
        sent_message = await message.answer(blocked_users)

        await drop_admin_message(message, sent_message)


limited_users_manager = LimitedUsersManager(INSPIRA_DB)


@dp.message_handler(commands=['limited_users'])
async def blacklist_cat_users(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
        await construction_to_delete_messages(message)

        blocked_users = await limited_users_manager.fetch_all_users()
        sent_message = await message.answer(blocked_users)

        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['block'])
async def block_user(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
        await construction_to_delete_messages(message)
        try:
            answer = await limited_users_manager.unblock_user(message.text)
            sent_message = await message.reply(f"<b>{answer}</b>", parse_mode='HTML')
        except Exception as e:
            sent_message = await message.reply("/// ERROR:", e)
        await drop_admin_message(message, sent_message)


@dp.message_handler(commands=['i'])
async def req_in_db(message: types.Message):
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
    if message.from_user.id in administrators.get_list_of_admins():
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
