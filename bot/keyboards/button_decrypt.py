from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup

from bot.callbacks.factories import SecureActionCallback


def decrypt_button(role: str, cache_key: str) -> InlineKeyboardMarkup:
    """
    Creates a 'Decrypt' button using the SecureActionCallback factory.

    The callback data will contain a short key referencing the full encrypted
    message stored in Redis.

    Args:
        role: The role of the user who will receive the button ('ir' or 'ie').
        cache_key: The unique key that references the encrypted data in Redis.

    Returns:
        An InlineKeyboardMarkup with a single 'Decrypt' button.
    """
    # The 'value' of the callback is now the short cache_key
    callback_data = SecureActionCallback(
        role=role,
        action="decrypt",
        value=cache_key,  # <-- The variable name now matches the meaning
    ).pack()

    button = InlineKeyboardButton(text="🔑 Прочитать", callback_data=callback_data)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
