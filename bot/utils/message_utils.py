from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.lexicon import DEVELOPER_CONTACT_URL
from bot.lexicon import HELP_TEXT


async def send_invitation_link_message(message: Message, deep_link_text: str):
    """
    Sends the generated deep link text to the user as a new message.
    This replaces the old 'invitation_link_created_message'.
    """
    await message.answer(text=deep_link_text)


async def send_help_message(event: Message | CallbackQuery):
    """
    Builds and sends the standard help message with a contact button.
    Can be called from a Message or CallbackQuery handler.
    """
    # 1. Create the keyboard with the developer contact button
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✉️ Связаться с разработчиком", url=DEVELOPER_CONTACT_URL
        )
    )

    # 2. Check the event type to decide how to respond
    if isinstance(event, Message):
        # If triggered by a command, send a new message
        await event.answer(
            text=HELP_TEXT,
            reply_markup=builder.as_markup(),
            disable_web_page_preview=True,
        )
    elif isinstance(event, CallbackQuery):
        # If triggered by a button, edit the existing message for a cleaner UX
        await event.message.edit_text(
            text=HELP_TEXT,
            reply_markup=builder.as_markup(),
            disable_web_page_preview=True,
        )
        await event.answer()
