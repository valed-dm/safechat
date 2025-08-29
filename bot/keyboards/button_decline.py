from aiogram.types import InlineKeyboardButton


def decline_button(role_action_id: str):
    """Prepare 'Decline' button to be used in the invitee's
    SecureTalk confirmation Keyboard"""
    button = InlineKeyboardButton(
        text="❌ Отклонить",
        callback_data=role_action_id,
    )
    return button
