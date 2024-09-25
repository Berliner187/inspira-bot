import os
import datetime
from time import sleep, time
from server_info import timing_decorator
from referral import RESOURCE_DICT
import asyncio

import sqlite3
import aiosqlite

from referral import RESOURCE_DICT
from tracer import TracerManager, TRACER_FILE


__version__ = "0.2.0"
DEBUG = True


# ============== ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ ==========================
tracer_l = TracerManager(TRACER_FILE)


INSPIRA_DB = 'inspira.db'
FILE_LIMITED_USERS = 'limited_users.db'

USERS_TABLE_NAME = 'users'
PRODUCTS_TABLE_NAME = 'products'
REFERRALS_TABLE_NAME = 'referrals'
LIMITED_USERS_TABLE_NAME = 'limited_users'
ADMINS_TABLE_NAME = 'admins'


FIELDS_FOR_USERS = [
    {'name': 'id', 'type': 'INTEGER PRIMARY KEY'},
    {'name': 'user_id', 'type': 'INTEGER'},
    {'name': 'fullname', 'type': 'TEXT'},
    {'name': 'phone', 'type': 'TEXT'},
    {'name': 'username', 'type': 'TEXT'},
    {'name': 'date_register', 'type': 'TEXT'},
    {'name': 'user_status', 'type': 'BOOL'},
    {'name': 'user_status_date_upd', 'type': 'TEXT'}
]
FIELDS_FOR_PRODUCTS = [
    {'name': 'id', 'type': 'INTEGER PRIMARY KEY'},
    {'name': 'product_id', 'type': 'TEXT'},
    {'name': 'status', 'type': 'TEXT'},
    {'name': 'user_id', 'type': 'INTEGER'},
    {'name': 'group_number', 'type': 'TEXT'},
    {'name': 'status_update_date', 'type': 'TEXT'}
]
FIELDS_FOR_REFERRALS = [
    {'name': 'id', 'type': 'INTEGER PRIMARY KEY'},
    {'name': 'user_id', 'type': 'TEXT'},
    {'name': 'arrival_id', 'type': 'TEXT'},
    {'name': 'date_arrival', 'type': 'TEXT'}
]
FIELDS_FOR_LIMITED_USERS = [
    {'name': 'id', 'type': 'INTEGER PRIMARY KEY'},
    {'name': 'user_id', 'type': 'INTEGER'},
    {'name': 'date', 'type': 'TEXT'}
]
FIELDS_FOR_ADMINS = [
    {'name': 'id', 'type': 'INTEGER PRIMARY KEY'},
    {'name': 'user_id', 'type': 'INTEGER'},
    {'name': 'security_clearance', 'type': 'INTEGER'},
    {'name': 'admin_status', 'type': 'BOOL'}
]


def get_format_date():
    return datetime.datetime.now().strftime("%d.%m.%Y-%H:%M:%S")


class TemplatesTrackingEvents(TracerManager):
    """
        Шаблоны отображения отработавших событий в консоли.
        Условие: DEBUG = True
    """
    def __init__(self, tracer_fields):
        super().__init__(tracer_fields)

    def _template_structure_message(self, status, message, more_info=''):
        if DEBUG:
            print(f"{status} -> {message} -- {more_info}", self.default_color)

    def event_success(self, message):
        self._template_structure_message(f"{self.color_info}[ OK ]", message)

    def event_warning(self, message, warning_message):
        self._template_structure_message(f"{self.color_warning}[ WARNING ]", message, warning_message)

    def event_error(self, message, error_message):
        self._template_structure_message(f"{self.color_error}[ ERROR ]", message, error_message)

    def event_handler(self, func):
        """
            Обработчик событий. Работает как декоратор.
            :param func:
            :return:
        """
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                self.event_success(func.__name__)
                self.tracer_charge(
                    "DB", 0,
                    f"{func.__module__} -> {func.__name__}",
                    "success")
                return result
            except TypeError or ValueError or KeyError or IndexError as warning:
                self.event_warning(func.__name__, str(warning))
                self.tracer_charge(
                    "WARNING", 0,
                    f"{func.__module__} -> {func.__name__}",
                    "something went wrong", f"{warning}")
                return None
            except Exception as error:
                self.event_error(func.__name__, str(error))
                self.tracer_charge(
                    "ERROR", 0,
                    f"{func.__module__} -> {func.__name__}",
                    "something went wrong", f"{error}")
                raise

        return wrapper


templates_status_events = TemplatesTrackingEvents(TRACER_FILE)


class DataBaseManager:
    def __init__(self, db_name):
        self.db_name = db_name

    @staticmethod
    def _sql_query_response_to_list(list_to_convert) -> list:
        result = [item[0] for item in list_to_convert]
        return result

    def __check_table_for_exists(self, table_name) -> bool:
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()
        conn.close()

        return result is not None

    def create_table(self, table_name: str, fields: list):
        if self.__check_table_for_exists(table_name):
            print(f"---- TABLE ({table_name}) in DATABASE ({self.db_name}) [ OK ] ----")
        else:
            print("=*=*=*=*=*=* WARNING =*=*=*=*=*=*")
            print(f"---- CREATE TABLE ({table_name}) in DATABASE ({self.db_name}) [ CREATE ] ----")
            try:
                __conn = sqlite3.connect(self.db_name)
                cur = __conn.cursor()

                field_definitions = []
                for field in fields:
                    field_name = field['name']
                    field_type = field['type']
                    field_definitions.append(f'{field_name} {field_type}')

                field_definitions_str = ', '.join(field_definitions)
                sql_query = f'CREATE TABLE IF NOT EXISTS {table_name} ({field_definitions_str})'

                cur.execute(sql_query)
                __conn.commit()
                __conn.close()

                print("----------- SUCCESS -----------")
                tracer_l.tracer_charge(
                    "DB", 0,
                    f"{self.__module__} -> {self.create_table.__name__}",
                    f"success create table – {table_name}")
                sleep(.25)
            except Exception as db_error:
                tracer_l.tracer_charge(
                    "DB", 0,
                    f"{self.__module__} -> {self.create_table.__name__}",
                    "error while trying create table", f"{db_error}")

    @templates_status_events.event_handler
    def add_record(self, table_name: str, data: dict):
        """
            Алгоритм добавления записи в любую таблицу.
            :param table_name: Название таблицы, в которую будет добавлена запись.
            :param data: Словарь. Ключи - имена столбцов, значения - данные для вставки.
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join('?' * len(data))
        values = tuple(data.values())

        if 'date_register' in data and data['date_register'] is None and data['user_status_date_upd'] is None:
            now = datetime.datetime.now()
            date_format = "%d-%m-%Y %H:%M:%S"
            data['date_register'] = now.strftime(date_format)
            data['user_status_date_upd'] = now.strftime(date_format)

        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})'
        cursor.execute(query, values)
        conn.commit()
        conn.close()

        if DEBUG:
            print(f"\nDataBaseManager -> add_record to table '{table_name}'")
            print(f"data: {data}")
            print(f"values: {values}")

    @templates_status_events.event_handler
    def find_by_condition(self, table_name: str, condition: str = None):
        """
        Метод поиска записей по условию в указанной таблице.
        :param table_name: Название таблицы, в которой будет происходить поиск.
        :param condition: Условие поиска (строка SQL). Например, "user_id = 123"
        :return: Список найденных записей (список кортежей).
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT * FROM {table_name}'
        if condition:
            query += f' WHERE {condition}'

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        if DEBUG:
            print(f"\nDatabaseManager -> find_by_condition in table '{table_name}'")
            print(f"query: {query}")
            print(f"results: {results}")

        return results


class ProductManager(DataBaseManager):
    @templates_status_events.event_handler
    def update_user_group(self, user_id: int, group_number: str, initial_status: str):
        """
        Обновляет номер группы и начальный статус пользователя в базе данных.
        :param user_id: ID пользователя, чью группу нужно обновить.
        :param group_number: Новый номер группы, который нужно установить.
        :param initial_status: Начальный статус пользователя, по умолчанию "в процессе".
        """
        print(f"Connecting to database: {self.db_name}")
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            now = datetime.datetime.now()
            status_update_date = now.strftime("%d-%m-%Y %H:%M:%S")

            query = '''
                UPDATE products
                SET group_number = ?, status = ?, status_update_date = ?
                WHERE user_id = ?
            '''
            cursor.execute(query, (group_number, initial_status, status_update_date, user_id))
            conn.commit()
            conn.close()

            if DEBUG:
                print(f"User {user_id} group updated to '{group_number}' and status set to '{initial_status}' "
                      f"at {status_update_date}")

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while updating user group for {user_id} -----")

    @templates_status_events.event_handler
    def update_product_id(self, user_id: int, product_id: int):
        """
            Обновляет номер изделия.
            :param user_id: ID пользователя, чье изделие нужно обновить.
            :param product_id: Уникальный номер изделия.
        """
        print(f"Connecting to database: {self.db_name}")
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            now = datetime.datetime.now()
            status_update_date = now.strftime("%d-%m-%Y %H:%M:%S")

            query = '''
                UPDATE products
                SET product_id = ?, status_update_date = ?
                WHERE user_id = ?
            '''
            cursor.execute(query, (product_id, status_update_date, user_id))
            conn.commit()
            conn.close()

            if DEBUG:
                print(f"SET product_id {product_id}  for {user_id}: OK")

        except Exception as e:
            if DEBUG:
                print(f"/_-_/ FAIL to SET product_id {product_id}  for {user_id}\n\n{e}")

    @templates_status_events.event_handler
    def update_product_status(self, user_id: int, new_status: str):
        """
        Обновляет статус пользователя в базе данных.
        :param user_id: ID пользователя, чей статус нужно обновить.
        :param new_status: Новый статус, который нужно установить.
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            now = datetime.datetime.now()
            status_update_date = now.strftime("%d-%m-%Y %H:%M:%S")

            query = '''
                    UPDATE products
                    SET status = ?, status_update_date = ?
                    WHERE user_id = ?
                '''
            cursor.execute(query, (new_status, status_update_date, user_id))
            conn.commit()
            conn.close()

            print(f"User {user_id} status updated to '{new_status}' at {status_update_date}")
            return True

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while updating user status for {user_id} -----")
            return False

    @templates_status_events.event_handler
    def get_product_status(self, user_id: int) -> str:
        """
            Получение статуса изделия.
            :param user_id: уникальный идентификатор пользователя
            :return: статус изделия – НЕ НАЧАТ, В ПРОЦЕССЕ, ГОТОВО, ПОЛУЧЕНО
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT status FROM {PRODUCTS_TABLE_NAME}'
        query += f' WHERE user_id = {user_id}'

        cursor.execute(query)
        status = cursor.fetchone()[0]
        conn.close()

        return status

    @templates_status_events.event_handler
    def get_all_groups(self) -> list:
        """
            Получение списка всех групп из БД.
            :return: список всех сохраненных групп.
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT * FROM {PRODUCTS_TABLE_NAME}'

        cursor.execute(query)
        list_users_data = cursor.fetchall()
        conn.close()

        return list_users_data

    @templates_status_events.event_handler
    def get_group(self, user_id: int):
        """
            Получение номера группы по идентификатору пользователя.
            :param user_id: уникальный идентификатор пользователя
            :return: номер группы
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT group_number FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
        cursor.execute(query, (user_id,))

        group_number = cursor.fetchone()[0]
        conn.close()

        return group_number

    @templates_status_events.event_handler
    def find_all_users_from_group(self, group_number: str) -> list:
        """ TODO: Отрефакторить название
            Выгрузка и получение всех пользователей из БД.
            :param group_number: номер группы
            :return: список всех пользователей одной группы
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT user_id FROM {PRODUCTS_TABLE_NAME} WHERE group_number = ?'
        cursor.execute(query, (group_number,))

        list_users_data = cursor.fetchall()

        conn.close()
        list_users_data = [item[0] for item in list_users_data]

        return list_users_data

    @templates_status_events.event_handler
    def get_user_product_card(self, user_id: int) -> dict:
        """
        Выгрузка и получение карточки пользователя:
        • номер изделия
        • статус изделия
        • номер группы
        • дата обновления записей
        :param user_id: уникальный идентификатор пользователя
        :return: словарь вышеперечисленных данных
        """
        # Используем контекстный менеджер для автоматического закрытия соединения
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            query = f'SELECT product_id, status, group_number, status_update_date FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
            cursor.execute(query, (user_id,))

            list_users_data = cursor.fetchone()

        if list_users_data is None:
            return {
                'product_id': 'пусто',
                'product_status': 'пусто',
                'group_id': 'пусто',
                'status_update_date': 'пусто'
            }

        return {
            'product_id': list_users_data[0],
            'product_status': list_users_data[1],
            'group_id': list_users_data[2],
            'status_update_date': list_users_data[3]
        }

    @staticmethod
    def get_user_product_card_for_display(user_product_card: dict, product_statuses: dict) -> str:
        if not user_product_card:
            return "Карточка пользователя не найдена."

        user_product_card_display = (
            f"\n• Статус изделия: <b>{product_statuses.get(user_product_card['product_status'], 'Не задан')}</b>\n"
            f"• Номер группы: <b>{user_product_card['group_id']}</b>\n"
            f"• Номер изделия: <b>{user_product_card['product_id']}</b>\n\n"
            f"<i>Обновлено {user_product_card['status_update_date']}</i>"
        )

        return user_product_card_display

    @templates_status_events.event_handler
    def get_product_id(self, user_id: int) -> str:
        """
            Получение номера изделия конкретного пользователя.
            :param user_id: уникальный идентификатор пользователя
            :return: номер изделия
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT product_id FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
        cursor.execute(query, (user_id,))

        user_product_id = str(cursor.fetchone())
        conn.close()

        return user_product_id[0]


class UserManager(DataBaseManager):

    @templates_status_events.event_handler
    def check_user_in_database(self, user_id: int):
        """
            Проверка пользователя на существование.
        :param user_id: идентификатор пользователя
        :return:
        """
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute(f"SELECT * FROM {USERS_TABLE_NAME} WHERE user_id = ?", (user_id,))
        result = __cursor.fetchone()

        __cursor.close()
        __connect.close()

        if result:
            return True
        else:
            return False

    @staticmethod
    def __format_phone(phone_number):
        try:
            digits = ''.join(filter(str.isdigit, phone_number))
            formatted_number = f"+{digits[0]} {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"
            return formatted_number
        except Exception:
            return

    @templates_status_events.event_handler
    def get_user_data(self, user_id: int):
        __cursor = sqlite3.connect(self.db_name).cursor()
        __cursor.execute(f"SELECT * FROM {USERS_TABLE_NAME} WHERE user_id = ?", (user_id,))

        find_user = __cursor.fetchone()
        print(find_user)

        return find_user

    @templates_status_events.event_handler
    def get_user_card(self, user_id: int, user_type: str):
        """
            Поиск и выгрузка данных о пользователе из БД.
            :user_id - идентификатор пользователя
            :user_type - тип пользователя: гость или администратор
        """
        find_user = self.get_user_data(user_id)

        result = ''
        if find_user:
            if find_user[6]:
                user_status = 'Активен'
            else:
                user_status = 'Не активен'

            result += f"Имя: {find_user[2]}\n"
            result += f"Телефон: {self.__format_phone(find_user[3])}\n"

            if user_type == 'user':
                result += f"Статус: {user_status}\n\n"
                result += f"<i>Обновлён {find_user[7]}</i>\n"
                result += f"Дата регистрации: {find_user[5]}\n"
            elif user_type == 'admin':
                result += f"<i>Обновлён {find_user[7]}</i>\n"

            return result

    @templates_status_events.event_handler
    def read_users_from_db(self):
        """
            Return all data about users from DB.
            return: list()
        """
        connect = sqlite3.connect(self.db_name)
        cursor = connect.cursor()

        cursor.execute("SELECT * FROM users")
        all_users = cursor.fetchall()

        cursor.close()
        connect.close()

        return all_users

    @templates_status_events.event_handler
    def drop_user_from_db(self, _user_id):
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute(f"DELETE FROM {USERS_TABLE_NAME} WHERE user_id = ?", (_user_id,))
        __connect.commit()

        __cursor.execute(f"DELETE FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?", (_user_id,))
        __connect.commit()

        __cursor.close()
        __connect.close()

    @templates_status_events.event_handler
    def update_user_status(self, user_id: int, new_status: str):
        """
        Обновляет статус пользователя в базе данных.
        :param user_id: ID пользователя, чей статус нужно обновить.
        :param new_status: Новый статус, который нужно установить.
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        now = datetime.datetime.now()
        status_update_date = now.strftime("%d-%m-%Y %H:%M:%S")

        query = '''
            UPDATE users
            SET status = ?, status_update_date = ?
            WHERE user_id = ?
        '''
        cursor.execute(query, (new_status, status_update_date, user_id))
        conn.commit()
        conn.close()

        print(f"User {user_id} status updated to '{new_status}' at {status_update_date}")

    @templates_status_events.event_handler
    def update_contact_info(self, user_id: int, phone: str):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = '''
            UPDATE users
            SET phone = ?
            WHERE user_id = ?
            '''

        cursor.execute(query, (phone, user_id))
        conn.commit()
        conn.close()

        print(f"User {user_id} contact success updated")

    @templates_status_events.event_handler
    def get_phone(self, user_id: int):
        _connect = sqlite3.connect(self.db_name)
        _cursor = _connect.cursor()

        query = f'SELECT phone FROM {USERS_TABLE_NAME} WHERE user_id = ?'
        _cursor.execute(query, (user_id,))

        phone_from_user = self._sql_query_response_to_list(_cursor.fetchone())
        _cursor.close()
        _connect.close()

        return phone_from_user

    @templates_status_events.event_handler
    def get_user_contact_info(self, user_id: int):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT * FROM {USERS_TABLE_NAME} WHERE user_id = ?'
        cursor.execute(query, (user_id,))

        user_contact_info = cursor.fetchone()
        conn.close()

        if user_contact_info[3] is None:
            phone_from_user = '-'
        else:
            phone_from_user = user_contact_info[3]

        user_contact_info_str = f"{user_contact_info[2]} – {phone_from_user}"

        return user_contact_info_str


class ReferralArrival(DataBaseManager):
    @timing_decorator
    def check_user_ref(self, user_id, id_arrival):
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        users_in_ref = self.load_user_ref()
        flag_user_in_ref = False
        for user_row in users_in_ref:
            if user_id in user_row:
                flag_user_in_ref = True
                break

        if flag_user_in_ref is False:
            __cursor.execute(f'INSERT INTO referral (user_id, id_arrival, date) VALUES (?, ?, ?)',
                             (user_id, id_arrival, get_format_date()))

        __connect.commit()
        __connect.close()

    def load_user_ref(self):
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute("SELECT * FROM referral")
        all_referral = __cursor.fetchall()

        __connect.commit()
        __connect.close()

        return all_referral

    def get_latest_referrals_records(self) -> list:
        """
            Выгрузка данных о рефералах
        """
        last_referrals = self.load_user_ref()
        sorted_refs = sorted(
            last_referrals,
            key=lambda x: datetime.datetime.strptime(x[3], "%d.%m.%Y-%H:%M:%S")
        )
        return sorted_refs

    def get_latest_referrals_records_formats(self, count_refs: int) -> str:
        """
            Форматированная выгрузка данных о рефералах
        """
        referrals = self.get_latest_referrals_records().__reversed__()

        cnt = 0
        refs = ''
        for ref in referrals:
            cnt += 1
            refs += f'{ref[1]} --- {RESOURCE_DICT[ref[2]]} --- {ref[3]}\n'
            if cnt >= count_refs:
                break

        return refs


class LimitedUsersManager(DataBaseManager):
    @timing_decorator
    async def block_user(self, command):
        user_block_id = command.split(' ')[1]

        async with aiosqlite.connect(self.db_name) as __conn:
            now = datetime.datetime.now()
            formatted_date = now.strftime("%d-%m-%Y")

            try:
                await __conn.execute(f'INSERT INTO {LIMITED_USERS_TABLE_NAME} (id, date) VALUES (?, ?)',
                                     (user_block_id, formatted_date))
                await __conn.commit()
            except sqlite3.IntegrityError as e:
                print("block_user:", e)

            return f'/// USER {user_block_id} ЛИКВИДИРОВАН ❌'

    @timing_decorator
    async def unblock_user(self, command):
        user_unblock_id = command.split(' ')[1]

        async with aiosqlite.connect(self.db_name) as _conn:
            cursor = await _conn.execute(f"SELECT * FROM {LIMITED_USERS_TABLE_NAME} WHERE id = ?", (user_unblock_id,))
            record = await cursor.fetchone()

            if record:
                await _conn.execute(f"DELETE FROM {LIMITED_USERS_TABLE_NAME} WHERE id = ?", (user_unblock_id,))
                await _conn.commit()
                return f"/// USER {user_unblock_id} UNBLOCKED ✅"
            else:
                return "/// USER not FOUND."

    @timing_decorator
    async def fetch_all_limited_users(self):
        async with aiosqlite.connect(self.db_name) as _conn:
            cursor = await _conn.execute(f"SELECT * FROM {LIMITED_USERS_TABLE_NAME}")
            records = await cursor.fetchall()

            users_manager = UserManager(INSPIRA_DB)

            response = '/// BLACKLIST ///\n\n'
            if records:
                for record in records:
                    user_contact = users_manager.get_user_contact_info(record[0])
                    response += f'{user_contact} от {record[2]}\n'
                return response
            else:
                response += "/// EMPTY ///"
                return response

    @timing_decorator
    async def check_user_for_block(self, _user_id) -> bool:
        async with aiosqlite.connect(self.db_name) as _conn:
            cursor = await _conn.execute(f"SELECT * FROM {LIMITED_USERS_TABLE_NAME} WHERE id = ?", (_user_id,))
            user_in_blacklist = await cursor.fetchone()
            print(user_in_blacklist)
            if user_in_blacklist:
                if _user_id == user_in_blacklist[0]:
                    return True
                else:
                    return False


class AdminsManager(DataBaseManager):
    @templates_status_events.event_handler
    def add_new_admin(self, new_admin_id: int, security_clearance: str) -> None:

        admin_data_to_db = {
            "user_id": new_admin_id,
            "security_clearance": security_clearance,
            "admin_status": True
        }

        self.add_record(ADMINS_TABLE_NAME, admin_data_to_db)

    @templates_status_events.event_handler
    def _get_security_clearance(self, user_id: int):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT security_clearance FROM {ADMINS_TABLE_NAME} WHERE user_id = ?'
        cursor.execute(query, (user_id,))

        security_clearance = int(cursor.fetchone()[0])
        conn.close()

        return security_clearance

    @templates_status_events.event_handler
    def check_security_clearance(self, user_id: int):
        security_clearances = {
            1: "Полный контроль и управление",
            2: "Только управление"
        }
        sc = self._get_security_clearance(user_id)

        return security_clearances[sc]

    @templates_status_events.event_handler
    def get_administrators_from_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT user_id FROM {ADMINS_TABLE_NAME} '
        cursor.execute(query)

        admin_list = self._sql_query_response_to_list(cursor.fetchall())
        conn.close()

        return admin_list

    @templates_status_events.event_handler
    def get_admin_status(self, admin_id: int):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        query = f'SELECT admin_status FROM {ADMINS_TABLE_NAME} WHERE user_id = ?'
        cursor.execute(query, (admin_id,))

        admin_status = self._sql_query_response_to_list(cursor.fetchone())
        print(admin_status)
        cursor.close()
        conn.close()

        return admin_status

    @templates_status_events.event_handler
    def drop_admin_from_db(self, admin_id: int):
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute(f"DELETE FROM {ADMINS_TABLE_NAME} WHERE user_id = ?", (admin_id,))
        __connect.commit()

        __cursor.close()
        __connect.close()


class StatControl(DataBaseManager):
    pass
