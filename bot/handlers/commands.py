from aiogram import Bot
from aiogram import Router
from aiogram.filters import Command
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from redis import Redis

from bot.core.config import settings
from bot.core.logging_setup import log
from bot.filters.is_in_conversation import IsInConversationFilter
from bot.keyboards.main_menu_keyboard import main_menu_keyboard
from bot.services.pubsub_service import PubSubService
from bot.utils.conversation_utils import propose_abort
from bot.utils.invitation_utils import present_invitation_to_invitee
from bot.utils.inviter_utils import initialize_inviter_workflow
from bot.utils.message_utils import send_help_message
from bot.utils.user_flow_utils import start_key_exchange_listener


router = Router(name="command-handlers")


@router.message(Command("help", ignore_mention=True))
async def handle_help_command(message: Message):
    """Handles the /help command by sending the help message."""
    await send_help_message(message)


@router.message(Command("start", ignore_mention=True))
async def handle_start_command(
    message: Message,
    state: FSMContext,
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
    command: CommandObject | None = None,
):
    """
    Handles all /start commands.
    - If a payload (deep link) is present, presents the invitation.
    - If no payload is present, initializes the user or shows the main menu.
    """
    if command and command.args:
        # --- ✅ /start with deep link ---
        secure_id = command.args
        invitee = message.from_user
        try:
            await present_invitation_to_invitee(
                invitee=invitee, secure_id=secure_id, bot=bot, redis=redis
            )
        except Exception as e:
            log.exception(f"Deep link presentation failed for user {invitee.id}")
            await message.answer(f"Не удалось обработать приглашение: {e}")
        # --- END OF REFACTOR ---
    else:
        # --- ✅ plain /start (This logic is already correct and functional) ---
        try:
            fsm_data = await state.get_data()
            if fsm_data.get("secure_id"):
                log.info(
                    f"User {message.from_user.id} sent"
                    f" /start while already in a session."
                )
                await message.answer(
                    "Вы уже в активной сессии. Главное меню:",
                    reply_markup=main_menu_keyboard,
                )
                return

            user_id = message.from_user.id
            await initialize_inviter_workflow(user_id, redis)
            await start_key_exchange_listener(user_id, pubsub)
            await message.answer(
                f"Вас приветствует {settings.LOGO} бот!",
                reply_markup=main_menu_keyboard,
            )
        except Exception:
            log.exception(f"Error in standard start for user {message.from_user.id}")
            await message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")


@router.message(Command("abort"), IsInConversationFilter())
async def handle_abort_command(
    message: Message,
    bot: Bot,
    recipient_id: int,
    secure_id: str,
    sender_prefix: str,
    recipient_prefix: str,
):
    """Handles /abort to propose ending a conversation."""
    # Note: recipient_id and other args are magically provided by our middleware!
    await propose_abort(
        message, bot, secure_id, recipient_id, sender_prefix, recipient_prefix
    )
