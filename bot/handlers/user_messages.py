from aiogram import Bot
from aiogram import F
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis

from bot.core.logging_setup import log
from bot.filters.is_in_conversation import IsInConversationFilter
from bot.states import ConversationStates
from bot.utils.conversation_utils import encrypt_and_relay_message
from bot.utils.invitation_utils import process_manual_username_input


router = Router(name="user-message-handlers")


@router.message(StateFilter(ConversationStates.entering_username), F.text)
async def handle_username_input(
    message: Message, state: FSMContext, bot: Bot, redis: Redis
):
    """
    Handles manual invitee's username input by calling the main
    orchestration utility.
    """
    try:
        await process_manual_username_input(message, state, bot, redis)
    except Exception as e:
        log.exception(
            f"Failed to process manual username input for user {message.from_user.id}"
        )
        await message.answer(f"Произошла непредвиденная ошибка: {e}")


# This is our handler for all secure text messages.
@router.message(F.text, IsInConversationFilter())
async def handle_secure_text(
    message: Message,
    bot: Bot,
    recipient_id: int,
    secure_id: str,
    recipient_prefix: str,
    redis: Redis,
):
    """Encrypts and relays messages for users in a secure conversation."""
    await encrypt_and_relay_message(
        message,
        bot,
        secure_id,
        recipient_id,
        recipient_prefix,
        redis,
    )


# @router.message()
# async def catch_all_unhandled_messages(message: Message):
#     """
#     This handler is for debugging. It catches any message that wasn't
#     processed by any other message handler.
#     """
#     print("--- DEBUG: CATCH-ALL HANDLER TRIGGERED ---")
#     print(f"Message Text: '{message.text}'")
#     print(f"Message Entities: {message.entities}")
#     await message.answer(
#         "<b>DEBUG MODE</b>\n"
#         "This message was not caught by any specific command or message handler. "
#         "Check the console logs for details."
#     )
