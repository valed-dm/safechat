from aiogram.types import InlineKeyboardButton

from bot.callbacks.factories import ConversationCallback
from bot.core.config import settings
from bot.utils.dynamic_keyboard import dynamic_keyboard


main_menu_buttons = [
    InlineKeyboardButton(
        text=f"{settings.LOGO}",
        callback_data=ConversationCallback(role="ir", action="prepare").pack(),
    ),
    InlineKeyboardButton(text="Настройки", callback_data="settings"),
    InlineKeyboardButton(text="Инфо", callback_data="help"),
]

main_menu_keyboard = dynamic_keyboard(main_menu_buttons, 3)
