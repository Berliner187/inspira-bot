from aiogram.dispatcher.filters.state import StatesGroup, State


class FormRegistrationForLesson(StatesGroup):
    date = State()
    time = State()
    activity = State()


class FormGroupProduct(StatesGroup):
    group = State()
    product_id = State()
    user_id = 0


class FormAddAdmin(StatesGroup):
    admin_user_id = State()
