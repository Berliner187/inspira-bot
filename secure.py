import sqlite3
import datetime
import time


from database_manager import LimitedUsersManager


__version__ = "0.1.0"


class SecureDivision:
    def __init__(self, blacklist_db):
        self.blacklist_db = blacklist_db
        self.cnt_notify_banned_users = []
        self.temporarily_blocked_users = {}
        self.user_messages = {}

    async def check_ban_users(self, user_id):
        connect_blocked = sqlite3.connect(self.blacklist_db)
        cursor = connect_blocked.cursor()
        cursor.execute("SELECT * FROM blacklist WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        connect_blocked.close()

        if result:
            if user_id not in self.cnt_notify_banned_users:
                self.cnt_notify_banned_users.append(user_id)
            return True
        else:
            return False

    async def block_user_temporarily(self, user_id) -> bool:
        self.temporarily_blocked_users[user_id] = datetime.datetime.now() + datetime.timedelta(minutes=90)
        return True

    async def check_temporary_block(self, user_id) -> bool:
        if user_id in self.temporarily_blocked_users:
            if datetime.datetime.now() > self.temporarily_blocked_users[user_id]:
                del self.temporarily_blocked_users[user_id]
                return False
            else:
                return True
        else:
            return False

    async def ban_request_restrictions(self, user_id):
        current_time = time.time()

        if user_id not in self.user_messages:
            self.user_messages[user_id] = []

        self.user_messages[user_id] = [t for t in self.user_messages[user_id] if current_time - t <= 30]
        self.user_messages[user_id].append(current_time)

        if len(self.user_messages[user_id]) >= 2:
            if len(self.user_messages[user_id]) == 32:
                command_block = '/ban ' + str(user_id)
                # block_manager = LimitedUsersManager()
                # await block_manager.block_user(command_block)
                return f"☠️ ЛИКВИДИРОВАН ❌"

            if await self.check_temporary_block(user_id) is False:
                await self.block_user_temporarily(user_id)
                self.user_messages[user_id] = []
