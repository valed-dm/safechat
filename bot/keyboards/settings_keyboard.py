from aiogram.types import InlineKeyboardButton

from bot.callbacks.factories import ConversationCallback
from bot.utils.dynamic_keyboard import dynamic_keyboard


invite_partner_button = InlineKeyboardButton(
    text="Пригласить",
    callback_data=ConversationCallback(role="ie", action="input").pack(),
)

reset_partners_button = InlineKeyboardButton(
    text="Удалить чаты",
    callback_data=ConversationCallback(role="ir", action="reset").pack(),
)

settings_menu_buttons = [invite_partner_button, reset_partners_button]
settings_menu_keyboard = dynamic_keyboard(settings_menu_buttons, 3)
