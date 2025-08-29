from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


def cancel_button(role_action_id: str):
    """Prepare Cancel button for inviter's reset SecureTalk state Keyboard
    if invitation is declined by invitee"""
    button = InlineKeyboardButton(
        text="❌ Отменить",
        callback_data=role_action_id,
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
