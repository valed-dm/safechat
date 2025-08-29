from aiogram import Bot
from aiogram import F
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton
from aiogram.types import User
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis import Redis

from bot.callbacks.factories import ConversationCallback
from bot.callbacks.factories import InvitationCallback
from bot.callbacks.factories import SecureActionCallback
from bot.core.config import settings
from bot.core.logging_setup import log
from bot.keyboards.inviter_contacts_keyboard import contacts_keyboard
from bot.keyboards.main_menu_keyboard import main_menu_keyboard
from bot.keyboards.settings_keyboard import settings_menu_keyboard
from bot.services.pubsub_service import PubSubService
from bot.states import ConversationStates
from bot.utils.conversation_utils import decrypt_and_show_message
from bot.utils.invitation_utils import process_invitation_acceptance
from bot.utils.invitation_utils import process_invitation_decline
from bot.utils.invitation_utils import reset_all_chats
from bot.utils.invitation_utils import start_direct_chat_session
from bot.utils.message_utils import send_help_message


router = Router(name="callback-handlers")


@router.callback_query(F.data == "help")
async def handle_help_callback(query: CallbackQuery):
    """Handles the 'Info' button click by sending the help message."""
    await send_help_message(query)


@router.callback_query(F.data == "settings")
async def handle_settings_callback(query: CallbackQuery):
    """Handles the 'Settings' button click."""
    # Use edit_text to replace the main menu with the settings menu
    await query.message.edit_text(
        "Вам доступны варианты:",
        reply_markup=settings_menu_keyboard,
    )
    await query.answer()


@router.callback_query(
    ConversationCallback.filter((F.role == "ir") & (F.action == "reset"))  # type: ignore
)
async def handle_reset_invitees(query: CallbackQuery, redis: Redis):
    """Handles the request to delete all the user's chats."""
    try:
        await reset_all_chats(query.from_user.id, redis)
        await query.message.edit_text(
            "✅ Все чаты удалены!", reply_markup=main_menu_keyboard
        )
    except Exception as e:
        log.exception(f"Failed to reset chats for user {query.from_user.id}")
        await query.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(
    ConversationCallback.filter((F.role == "ir") & (F.action == "prepare"))  # type: ignore
)
async def handle_prepare_talk(query: CallbackQuery, redis: Redis):
    """
    Handles the click on the main 'Secure Talk' button by showing contact options.
    """
    user_id = query.from_user.id

    # 1. Get the keyboard and the number of contacts
    contacts_kb, num_contacts = await contacts_keyboard(user_id, redis)

    # 2. Use InlineKeyboardBuilder to add a "Manual Input" button
    builder = InlineKeyboardBuilder.from_markup(contacts_kb)
    builder.row(
        InlineKeyboardButton(
            text="Ручной ввод",
            callback_data=ConversationCallback(role="ie", action="input").pack(),
        )
    )

    # 3. CORRECTED: Define the message text based on whether contacts exist
    if num_contacts > 0:
        text = "Выберите контакт из списка или добавьте новый:"
    else:
        text = "У вас нет активных чатов. Пригласите собеседника, нажав 'Ручной ввод'."

    # 4. Call edit_text with the real text string
    await query.message.edit_text(
        text=text,  # <-- The placeholder '...' is now replaced with our text
        reply_markup=builder.as_markup(),
    )

    # 5. Acknowledge the click to remove the loading spinner
    await query.answer()


@router.callback_query(
    ConversationCallback.filter((F.role == "ie") & (F.action == "input"))  # type: ignore
)  # type: ignore
async def handle_manual_input(query: CallbackQuery, state: FSMContext):
    """
    Initiates the manual entry of an invitee's username by setting the FSM state.
    """
    # 1. Set the user's state to 'entering_username'
    await state.set_state(ConversationStates.entering_username)

    # 2. Edit the previous message to prompt the user for input
    await query.message.edit_text(
        "🔍 Введите имя пользователя (@username):",
        reply_markup=None,  # Remove the old keyboard
    )

    # 3. Formally acknowledge the button click
    await query.answer()


@router.callback_query(
    ConversationCallback.filter((F.role == "ir") & (F.action == "invite"))  # type: ignore
)
async def handle_invitee_button_click(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
    callback_data: ConversationCallback,
):
    """Handles an inviter's click on an existing contact to start a chat directly."""
    inviter: User = query.from_user
    invitee_id = int(callback_data.value)

    try:
        await query.message.edit_text("Устанавливаем безопасное соединение...")

        await start_direct_chat_session(
            inviter=query.from_user,
            invitee_id=int(callback_data.value),
            inviter_state=state,
            bot=bot,
            redis=redis,
            pubsub=pubsub,
        )

    except Exception as e:
        log.exception(
            f"Direct chat failed for inviter {inviter.id} to invitee {invitee_id}: {e}"
        )
        await query.answer(f"Ошибка при запуске чата: {e}", show_alert=True)


# Handler for when an invitee clicks "❌ Отклонить"
@router.callback_query(InvitationCallback.filter(F.action == "decline"))
async def handle_decline_click(
    query: CallbackQuery,
    bot: Bot,
    redis: Redis,
    callback_data: InvitationCallback,
):
    """
    Handles the invitee's decision to decline an invitation by calling
    the main processing utility function.
    """
    try:
        # The secure_id comes directly from the button's callback data
        secure_id = callback_data.value

        # --- ✅ THE REFACTOR ---
        # Replace the Invitation class logic with a direct call to our utility function.
        # This function handles notifying the inviter about the decline.
        await process_invitation_decline(
            invitee=query.from_user, secure_id=secure_id, bot=bot, redis=redis
        )
        # --- END OF REFACTOR ---

        # The UI feedback remains the same
        await query.message.delete()
        await query.answer("Вы отклонили приглашение.")

    except Exception as e:
        log.exception(
            f"Failed to process invitation decline for user {query.from_user.id}"
        )
        await query.answer(f"Ошибка при обработке приглашения: {e}", show_alert=True)


# Handler for when an inviter clicks "❌ Отменить" after a decline
@router.callback_query(
    ConversationCallback.filter((F.role == "ir") & (F.action == "cancel"))  # type: ignore
)
async def handle_cancel_click(query: CallbackQuery, state: FSMContext):
    """Handles the inviter's cancellation of a pending invitation."""
    try:
        # --- ✅ NATIVE STATE USAGE ---
        # Clear the state for the inviter who cancelled.
        await state.clear()
        await query.message.edit_text("Приглашение отозвано.")
    except Exception as e:
        log.exception("Failed to process invitation cancellation")
        await query.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(SecureActionCallback.filter(F.action == "decrypt"))  # type: ignore
async def handle_decrypt_click(
    query: CallbackQuery,
    state: FSMContext,
    callback_data: SecureActionCallback,
    redis: Redis,
):
    """Handles clicks on any 'decrypt' button."""
    try:
        # The encrypted data is directly in callback_data.value
        await decrypt_and_show_message(
            query, state, redis=redis, cache_key=callback_data.value
        )
    except Exception as e:
        log.exception(f"Error during decryption for user {query.from_user.id}: {e}")
        await query.answer(f"Error: {e}", show_alert=True)


@router.callback_query(SecureActionCallback.filter(F.action == "abort"))  # type: ignore
async def handle_abort_click(query: CallbackQuery, state: FSMContext):
    """Handles clicks on the 'abort' button from either participant."""
    try:
        # --- ✅ NATIVE STATE USAGE ---
        # 1. Read the data directly
        fsm_data = await state.get_data()
        inviter_username = fsm_data.get("inviter_username")
        invitee_username = fsm_data.get("invitee_username")

        if not inviter_username:  # A simple check to see if state exists
            raise ValueError("No active conversation to abort.")

        # 2. Clear the state
        await state.clear()

        # 3. Construct the final message
        msg = f"{settings.LOGO} @{inviter_username}❌@{invitee_username} завершен!"
        await query.message.edit_text(msg, reply_markup=None)

    except ValueError as e:
        await query.answer(str(e), show_alert=True)
    except Exception as e:
        log.exception(
            f"Unexpected error during conversation abort for user"
            f" {query.from_user.id}: {e}"
        )
        await query.answer("Произошла непредвиденная ошибка.", show_alert=True)


# This handler is for when an invitee clicks "✅ Участвовать"
@router.callback_query(InvitationCallback.filter(F.action == "accept"))
async def handle_confirm_click(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
    callback_data: InvitationCallback,
):
    """
    Handles the invitee's confirmation to join a secure chat by calling the
    main processing utility function.
    """
    try:
        # The secure_id comes directly from the button's callback data
        secure_id = callback_data.value

        # --- ✅ THE REFACTOR ---
        # Replace the SecureSession logic with a direct call to our utility function.
        # This function contains all the necessary steps for establishing the session.
        await process_invitation_acceptance(
            invitee=query.from_user,
            secure_id=secure_id,
            state=state,
            bot=bot,
            redis=redis,
            pubsub=pubsub,
        )
        # --- END OF REFACTOR ---

        # The UI feedback remains the same
        await query.message.delete()
        await query.answer("Вы приняли приглашение!")

    except Exception as e:
        log.exception(
            f"Failed to process invitation acceptance for user" f" {query.from_user.id}"
        )
        await query.answer(f"Ошибка при обработке приглашения: {e}", show_alert=True)


@router.callback_query(
    ConversationCallback.filter((F.role == "ir") & (F.action == "start"))  # type: ignore
)
async def handle_start_chat_click(
    query: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    callback_data: ConversationCallback,
):
    """
    Handles the final click from the inviter to officially 'open' the chat.
    Shows the secure input keyboard to both users.
    """
    # The FSM state is already set for both users. We just need the usernames.
    fsm_data = await state.get_data()
    inviter_username = fsm_data.get("inviter_username")
    invitee_username = fsm_data.get("invitee_username")
    invitee_id = int(callback_data.value)  # Get the invitee's ID from the button

    if not all([inviter_username, invitee_username]):
        await query.answer("Ошибка: не удалось найти данные сессии.", show_alert=True)
        return

    message_text = "✅ Безопасное соединение установлено. Вы можете начать общение."

    try:
        # Edit the inviter's message to show the final confirmation
        await query.message.edit_text(message_text)

        # Send the final confirmation to the invitee
        await bot.send_message(chat_id=invitee_id, text=message_text)
        await query.answer()

    except Exception:
        log.exception("Failed to send final start-chat notifications.")
        await query.answer("Произошла ошибка при запуске чата.", show_alert=True)
