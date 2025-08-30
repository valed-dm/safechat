from aiogram import Bot
from aiogram import F
from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis.asyncio import Redis

from bot.core.logging_setup import log
from bot.states import ConversationStates
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
