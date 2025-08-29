from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from bot.callbacks.factories import SecureActionCallback
from bot.core.config import settings


def abort_button(role: str, secure_id: str) -> InlineKeyboardMarkup:
    """
    Creates an 'Abort' button using the SecureActionCallback factory.

    Args:
        role: The role of the user, 'ir' or 'ie'.
        secure_id: The ID of the secure session to abort.

    Returns:
        An InlineKeyboardMarkup with a single 'Abort' button.
    """
    callback_data = SecureActionCallback(
        role=role, action="abort", value=secure_id
    ).pack()

    button = InlineKeyboardButton(
        text=f"❌ Прервать {settings.LOGO}", callback_data=callback_data
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
