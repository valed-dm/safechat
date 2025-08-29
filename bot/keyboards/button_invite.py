from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


invite_partner_button = InlineKeyboardButton(
    text="Пригласить",
    callback_data="ie:input:",
)


def invite_button():
    return InlineKeyboardMarkup(inline_keyboard=[[invite_partner_button]])
