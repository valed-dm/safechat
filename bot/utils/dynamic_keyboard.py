from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


def dynamic_keyboard(buttons: list[InlineKeyboardButton], buttons_per_row: int):
    rows = [
        buttons[i : i + buttons_per_row]
        for i in range(0, len(buttons), buttons_per_row)
    ]

    return InlineKeyboardMarkup(inline_keyboard=rows)
