from aiogram.types import InlineKeyboardButton

from bot.core.config import settings


def confirm_button(role_action_id: str):
    """Prepare 'Confirm' button to be used in the invitee's
    SecureTalk confirmation Keyboard"""
    button = InlineKeyboardButton(
        text=f"✅ Участвовать в {settings.LOGO}",
        callback_data=role_action_id,
    )
    return button
