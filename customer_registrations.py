from aiogram import Bot, Dispatcher, types
import datetime


class ManagerCustomerReg:
    """ Сущность, управляющая отображением данных при записи на занятие """
    def get_days_week_for_reg(self):
        today = datetime.date.today()

        days_ahead = 5 - today.weekday()
        if days_ahead < 0:
            days_ahead += 7
        first_saturday = today + datetime.timedelta(days=days_ahead)

        return [first_saturday + datetime.timedelta(weeks=i) for i in range(4)]

    def formatting_buttons_for_display(self):
        """
            Подгон кнопок под нормальное отображение.
            Располагаются по 2 кнопки на линии.
        """
        date_buttons = types.ReplyKeyboardMarkup(resize_keyboard=True)
        row_buttons = []

        for i, saturday in enumerate(self.get_days_week_for_reg()):
            button = types.KeyboardButton(saturday.strftime("%-d %B"))
            row_buttons.append(button)

            if len(row_buttons) == 2:
                date_buttons.row(*row_buttons)
                row_buttons = []

        if row_buttons:
            date_buttons.row(*row_buttons)

        return date_buttons

    @staticmethod
    def formatting_date_reg(date_str: str) -> dict:
        """
            Форматирование даты для отображения в шаблоне.
            ex. {day: 26, month: СЕН}
            :param date_str: str, ex. 26 сентября
            :return: dict, {day: 26, month: СЕН}
        """
        day = date_str.split(" ")[0]
        month = date_str.split(" ")[1].upper()[:3]

        return {"day": day, "month": month}

    @staticmethod
    def formatting_date_reg_for_database(date_str: str) -> str:
        """
            Форматирование даты для сохранения в БД.
            ex. 26.09.2024
            :param date_str: str, ex. 26 сентября
            :return: str, ex. 26.09.2024
        """
        date_format = "%d %B"
        date_obj = datetime.datetime.strptime(date_str, date_format)

        formatted_date = date_obj.strftime(f"%d.%m.{datetime.datetime.now().strftime('%Y')}")

        return formatted_date
