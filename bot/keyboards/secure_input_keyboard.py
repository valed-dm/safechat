from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


def secure_input_keyboard(partner_username: str) -> InlineKeyboardMarkup:
    """
    Creates a keyboard with a button that switches the user to inline mode
    to send a secure message to their partner.
    """

    # The 'switch_inline_query_current_chat' parameter tells Telegram:
    # "When this button is clicked, pre-fill the user's input box with this text
    #  and activate inline mode for my bot in this same chat."
    button_text = f"🔒 Отправить сообщение @{partner_username}"
    query_text = ""  # We can leave this empty for a cleaner user experience

    button = InlineKeyboardButton(
        text=button_text, switch_inline_query_current_chat=query_text
    )

    return InlineKeyboardMarkup(inline_keyboard=[[button]])
