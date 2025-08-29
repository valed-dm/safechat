from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup
from redis import Redis

from bot.callbacks.factories import ConversationCallback
from bot.utils.dynamic_keyboard import dynamic_keyboard
from bot.utils.inviter_utils import get_inviter_partners


async def contacts_keyboard(
    inviter_id: int,
    redis: Redis,
) -> tuple[InlineKeyboardMarkup, int]:
    """
    Generates a keyboard with buttons for each of the inviter's partners.
    """
    contacts = await get_inviter_partners(inviter_id, redis)

    buttons = []
    for contact in contacts:
        callback_data = ConversationCallback(
            role="ir",
            action="invite",
            value=str(contact["invitee_id"]),
        ).pack()

        buttons.append(
            InlineKeyboardButton(
                text=f"🔒 {contact['username']}", callback_data=callback_data
            )
        )

    return dynamic_keyboard(buttons, 3), len(contacts)
