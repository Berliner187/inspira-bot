from aiogram import Bot, Dispatcher, types
import datetime


class ManagerCustomerReg:
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
