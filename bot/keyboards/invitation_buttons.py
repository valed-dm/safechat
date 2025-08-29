from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from bot.callbacks.factories import ConversationCallback
from bot.callbacks.factories import InvitationCallback
from bot.core.config import settings


def confirm_button(secure_id: str) -> InlineKeyboardButton:
    """Creates a 'Confirm' button using the InvitationCallback factory."""
    return InlineKeyboardButton(
        text=f"✅ Участвовать в {settings.LOGO}",
        callback_data=InvitationCallback(action="accept", value=secure_id).pack(),
    )


def decline_button(secure_id: str) -> InlineKeyboardButton:
    """Creates a 'Decline' button using the InvitationCallback factory."""
    return InlineKeyboardButton(
        text="❌ Отклонить",
        callback_data=InvitationCallback(action="decline", value=secure_id).pack(),
    )


def start_chat_button(invitee_id: int, invitee_username: str) -> InlineKeyboardMarkup:
    """
    Creates a button for an inviter to start a chat with an invitee.
    This uses the new 'start' action.
    """
    callback_data = ConversationCallback(
        role="ir", action="start", value=str(invitee_id)
    ).pack()

    button = InlineKeyboardButton(
        text=f"🔒 Начать чат с @{invitee_username}", callback_data=callback_data
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
