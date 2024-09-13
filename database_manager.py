import os
import datetime
from time import sleep, time
from server_info import timing_decorator
from referral import RESOURCE_DICT
import asyncio

import sqlite3
import aiosqlite

from referral import RESOURCE_DICT


__version__ = "0.1.3"
DEBUG = True


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
    {'name': 'security_clearance', 'type': 'TEXT'},
    {'name': 'admin_status', 'type': 'TEXT'}
]


def get_format_date():
    return datetime.datetime.now().strftime("%d.%m.%Y-%H:%M:%S")


class DataBaseManager:
    def __init__(self, db_name):
        self.db_name = db_name

    def __check_exist_table(self, table_name: str):
        """
            Проверка на существование таблицы
        :param table_name:
        :return:
        """
        __conn = sqlite3.connect(self.db_name)
        cur = __conn.cursor()

        exist_table = cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")

        __conn.commit()
        __conn.close()

        if exist_table:
            return True
        else:
            return False

    def create_table(self, table_name: str, fields: list):
        if self.__check_exist_table:
            print(f"--*-- [ OK ] TABLE ({table_name}) in DATABASE ({self.db_name}) --*--")
            sleep(.25)
        else:
            print("=*=*=*=*=*=* WARNING =*=*=*=*=*=*")
            print(f"---- CREATE TABLE ({table_name}) in DATABASE ({self.db_name}) [ CREATE ] ----")

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

    def add_record(self, table_name: str, data: dict):
        """
            Алгоритм добавления записи в любую таблицу.
            :param table_name: Название таблицы, в которую будет добавлена запись.
            :param data: Словарь. Ключи - имена столбцов, значения - данные для вставки.
        """
        try:
            columns = ', '.join(data.keys())
            placeholders = ', '.join('?' * len(data))
            values = tuple(data.values())

            if 'date_register' in data and data['date_register'] is None:
                now = datetime.datetime.now()
                data['date_register'] = now.strftime("%d-%m-%Y %H:%M:%S")

            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})'
            cursor.execute(query, values)
            conn.commit()
            conn.close()

            if DEBUG:
                print(f"\nDataBaseManager -> add_record to table '{table_name}'")
                print(f"data: {data}")
                print(f"query: {query}")
                print(f"values: {values}")

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while adding record to {table_name} -----")

    def find_by_condition(self, table_name: str, condition: str = None):
        """
        Метод поиска записей по условию в указанной таблице.
        :param table_name: Название таблицы, в которой будет происходить поиск.
        :param condition: Условие поиска (строка SQL). Например, "user_id = 123" или "username LIKE 'ivanov'".
        :return: Список найденных записей (список кортежей).
        """
        try:
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

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while finding records in {table_name} -----")
            return []


db_manager = DataBaseManager(INSPIRA_DB)
db_manager.create_table(USERS_TABLE_NAME, FIELDS_FOR_USERS)
db_manager.create_table(PRODUCTS_TABLE_NAME, FIELDS_FOR_PRODUCTS)
db_manager.create_table(REFERRALS_TABLE_NAME, FIELDS_FOR_REFERRALS)
db_manager.create_table(LIMITED_USERS_TABLE_NAME, FIELDS_FOR_LIMITED_USERS)
db_manager.create_table(ADMINS_TABLE_NAME, FIELDS_FOR_ADMINS)


class ProductManager(DataBaseManager):
    def update_user_group(self, user_id: int, group_number: str, initial_status: str):
        """
        Обновляет номер группы и начальный статус пользователя в базе данных.
        :param user_id: ID пользователя, чью группу нужно обновить.
        :param group_number: Новый номер группы, который нужно установить.
        :param initial_status: Начальный статус пользователя, по умолчанию "в процессе".
        """
        if DEBUG:
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

            print(f"SET product_id {product_id}  for {user_id}: OK")

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"/_-_/ SET product_id {product_id}  for {user_id}: FAIL\n\n{e}")

    @timing_decorator
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

    def get_product_status(self, user_id: int) -> str:
        """
            Получение статуса изделия.
            :param user_id: уникальный идентификатор пользователя
            :return: статус изделия – НЕ НАЧАТ, В ПРОЦЕССЕ, ГОТОВО, ПОЛУЧЕНО
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT status FROM {PRODUCTS_TABLE_NAME}'
            query += f' WHERE user_id = {user_id}'

            cursor.execute(query)
            status = cursor.fetchone()[0]
            conn.close()

            return status

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get user status for {user_id} -----")

    def get_all_groups(self) -> list:
        """
            Получение списка всех групп из БД.
            :return: список всех сохраненных групп.
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT * FROM {PRODUCTS_TABLE_NAME}'

            cursor.execute(query)
            list_users_data = cursor.fetchall()
            conn.close()

            return list_users_data
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get all groups -----")

    def get_group(self, user_id: int):
        """
            Получение номера группы по идентификатору пользователя.
            :param user_id: уникальный идентификатор пользователя
            :return: номер группы
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT group_number FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
            cursor.execute(query, (user_id,))

            group_number = cursor.fetchone()[0]
            conn.close()

            return group_number
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while find group by user -----")

    def find_all_users_from_group(self, group_number: str) -> list:
        """ TODO: Отрефакторить название
            Выгрузка и получение всех пользователей из БД.
            :param group_number: номер группы
            :return: список всех пользователей одной группы
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT user_id FROM {PRODUCTS_TABLE_NAME} WHERE group_number = ?'
            cursor.execute(query, (group_number,))

            list_users_data = cursor.fetchall()

            conn.close()
            list_users_data = [item[0] for item in list_users_data]

            return list_users_data
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while find all users from group -----")

    def get_user_card(self, user_id: int) -> dict:
        """
            Выгрузка и получение карточки пользователя:
            • номер изделия
            • статус изделия
            • номер группы
            • дата обновления записей
            :param user_id: уникальный идентификатор пользователя
            :return: словарь вышеперечисленных данных
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT * FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
            cursor.execute(query, (user_id,))

            list_users_data = cursor.fetchone()

            card_user = {
                'product_id': list_users_data[1],
                'product_status': list_users_data[2],
                'group_id': list_users_data[4],
                'update_product_status': list_users_data[5]
            }
            conn.close()

            return card_user
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get user card -----")

    def get_product_id(self, user_id: int) -> str:
        """
            Получение номера изделия конкретного пользователя.
            :param user_id: уникальный идентификатор пользователя
            :return: номер изделия
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT product_id FROM {PRODUCTS_TABLE_NAME} WHERE user_id = ?'
            cursor.execute(query, (user_id,))

            user_product_id = str(cursor.fetchone())
            conn.close()

            return user_product_id[0]
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get user card -----")


class UserManager(DataBaseManager):

    def check_user_in_database(self, user_id: int):
        """
            Проверка пользователя на существование.
        :param user_id: идентификатор пользователя
        :return:
        """
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = __cursor.fetchone()

        __cursor.close()
        __connect.close()

        if result:
            return True
        else:
            return False

    def find_users_in_db(self, id_user):
        """
            Поиск и выгрузка данных о пользователе из БД
            id_user - идентификатор пользователя.
            user_id или fullname.
        """
        __cursor = sqlite3.connect(self.db_name).cursor()

        if len(str(id_user)) <= 20:
            __cursor.execute("SELECT * FROM users WHERE user_id = ?", (id_user,))
            find_users = __cursor.fetchone()

            result = ''
            if find_users:
                for item in range(len(find_users)):
                    if item == 0:
                        result += f"[{find_users[item]}] "
                    else:
                        result += f"{find_users[item]} "
                return result
            else:
                __cursor.execute("SELECT * FROM users WHERE fullname = ?", (id_user,))
                fetch_by_name = __cursor.fetchall()
                __cursor.close()
                if fetch_by_name:
                    if 0 < len(fetch_by_name) < 2:
                        for items in fetch_by_name:
                            for item in range(len(items)):
                                if item == 0:
                                    result += f"[{items[item]}] "
                                else:
                                    result += f"{items[item]} "
                    else:
                        for items in fetch_by_name:
                            for item in items:
                                result += f"{item} "
                            result += '\n'
                    return result
                else:
                    return False
        else:
            return "OverflowError: Python int too large to convert to SQLite INTEGER"

    @timing_decorator
    def load_all_users(self):
        """
            Display data about users from database
            Only print
            return: None
        """
        connect = sqlite3.connect(self.db_name)
        cursor = connect.cursor()

        cursor.execute("SELECT * FROM users")
        all_users = cursor.fetchall()

        for user in all_users:
            for i in range(len(user)):
                if i == len(user) - 1:
                    print(user[i], end="")
                else:
                    print(user[i], end=" --- ")
            print()

    @timing_decorator
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

    @timing_decorator
    def drop_user_from_db(self, _user_id):
        __connect = sqlite3.connect(self.db_name)
        __cursor = __connect.cursor()

        __cursor.execute(f"DELETE FROM users WHERE user_id=?", (_user_id,))
        __connect.commit()

        __cursor.close()
        __connect.close()

    @timing_decorator
    def load_database(self, name_database, display=False):
        """
            Reading old database (users.db) and return list with info about users.
            return: list - with users
        """
        _connect = sqlite3.connect(name_database)
        _connect = _connect.cursor()
        _connect.execute("SELECT * FROM users")
        all_users = _connect.fetchall()

        _connect.close()

        if display:
            for i in all_users:
                print(i)

        return all_users

    @timing_decorator
    def update_user_status(self, user_id: int, new_status: str):
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
                UPDATE users
                SET status = ?, status_update_date = ?
                WHERE user_id = ?
            '''
            cursor.execute(query, (new_status, status_update_date, user_id))
            conn.commit()
            conn.close()

            print(f"User {user_id} status updated to '{new_status}' at {status_update_date}")

        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while updating user status for {user_id} -----")

    def update_contact_info(self, user_id: int, phone: str):
        try:
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
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while updating phone for {user_id} -----")

    @staticmethod
    def __format_number(phone_number) -> str:
        str_phone_number = str(phone_number)
        str_number = (f"+{str_phone_number[0]} {str_phone_number[1:4]} {str_phone_number[4:7]} {str_phone_number[8:10]} "
                      f"{str_phone_number[11:12]} {str_phone_number[13:14]}")
        return str_number

    def get_phone(self, user_id: int) -> str:
        try:
            _connect = sqlite3.connect(self.db_name)
            _cursor = _connect.cursor()

            query = f'SELECT phone FROM {USERS_TABLE_NAME} WHERE user_id = ?'
            _cursor.execute(query, (user_id,))

            phone_from_user = _cursor.fetchone()[0]
            _cursor.close()
            _connect.close()

            return self.__format_number(phone_from_user)
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get phone from user -----")

    def get_user_contact_info(self, user_id: int):
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = f'SELECT * FROM {USERS_TABLE_NAME} WHERE user_id = ?'
            cursor.execute(query, (user_id,))

            user_contact_info = cursor.fetchone()
            conn.close()

            user_contact_info_str = f"{user_contact_info[2]} – {user_contact_info[3]}"

            return user_contact_info_str
        except Exception as e:
            print("---------- ERROR ----------")
            print(f"----- {e} while get contact info from user -----")


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
    async def fetch_all_users(self):
        async with aiosqlite.connect(self.db_name) as _conn:
            cursor = await _conn.execute(f"SELECT * FROM {LIMITED_USERS_TABLE_NAME}")
            records = await cursor.fetchall()

            response = '/// BLACKLIST ///\n\n'
            if records:
                for record in records:
                    response += f'{record[0]} от {record[2]}\n'
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
    def grant_rights_to_admin(self, superuser_id: int):
        pass
