import json

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardButton
from aiogram.types import Message
from aiogram.types import User
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis import Redis

from bot.callbacks.factories import ConversationCallback
from bot.core.config import settings
from bot.core.logging_setup import log
from bot.keyboards.button_cancel import cancel_button
from bot.keyboards.invitation_buttons import confirm_button
from bot.keyboards.invitation_buttons import decline_button
from bot.keyboards.invitation_buttons import start_chat_button
from bot.keyboards.inviter_contacts_keyboard import contacts_keyboard
from bot.services.pubsub_service import PubSubService
from bot.utils.crypto_utils import encrypt_symmetric_key_with_rsa
from bot.utils.crypto_utils import generate_symmetric_key
from bot.utils.crypto_utils import save_symmetric_key
from bot.utils.inviter_utils import setup_new_invitation
from bot.utils.inviter_utils import store_inviter_conversation
from bot.utils.message_utils import send_invitation_link_message


INVITATION_TTL = 3600
PARTNER_DATA_TTL = 86400 * 30  # 30 days


async def generate_invitee_deep_link(
    inviter: User, invitee_username: str, bot: Bot, redis: Redis
) -> str:
    """
    Generates a deep link for a specific invitee.
    This replaces the old 'invitee_deep_link' function.
    """
    # 1. Prepare a new invitation and get the unique secure_id
    secure_id = await setup_new_invitation(inviter.id, inviter.username, redis)

    # 2. Get the bot's own username dynamically
    me = await bot.get_me()
    bot_username = me.username

    # 3. Construct the link and the message text
    deep_link = f"https://t.me/{bot_username}?start={secure_id}"
    deep_link_text = (
        f"Перешлите {settings.LOGO} ссылку '{invitee_username}' "
        f"от '@{inviter.username}':\n{deep_link}"
    )

    return deep_link_text


async def process_invitation_deeplink(
    invitee: User,
    secure_id: str,
    state: FSMContext,  # This is the FSMContext for the invitee
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
):
    """
    Handles the entire deep link invitation flow after an invitee clicks the link.

    This refactored function ensures the FSM state is set symmetrically for
    both the inviter and the invitee.
    """
    log.info(f"Invitation received by @{invitee.username} with secure_id {secure_id}.")

    # 1. Resolve the invitation to get the inviter's details from Redis
    try:
        inviter_id, inviter_username, inviter_public_pem = await get_invitation_details(
            secure_id,
            redis,
        )
    except ValueError as e:
        log.warning(f"Failed to resolve invitation for secure_id {secure_id}: {e}")
        await bot.send_message(
            invitee.id, "Эта ссылка-приглашение недействительна или истекла."
        )
        return

    # 2. Prevent users from accepting their own invitations
    if invitee.id == inviter_id:
        log.warning(
            f"User {invitee.id} (@{invitee.username})"
            f" tried to accept their own invitation."
        )
        await bot.send_message(
            chat_id=invitee.id,
            text="Вы не можете принять собственное приглашение."
            " Пожалуйста, перешлите эту ссылку вашему собеседнику.",
        )
        return

    # 3. Perform the cryptographic setup (invitee generates & encrypts AES key)
    # This also notifies the inviter's background listener via Pub/Sub.
    await setup_conversation_crypto(
        inviter_public_pem=inviter_public_pem,
        inviter_id=inviter_id,
        invitee_id=invitee.id,
        secure_id=secure_id,
        redis=redis,
        pubsub=pubsub,
    )

    # --- ✅ THE CRITICAL FIX: Set FSM State for BOTH users ---

    # 4. Prepare the shared session data in a dictionary
    session_data = {
        "secure_id": secure_id,
        "inviter_id": inviter_id,
        "inviter_username": inviter_username,
        "invitee_id": invitee.id,
        "invitee_username": invitee.username,
    }

    # 5. Set the state for the invitee (the user who performed the action)
    await state.set_data(session_data)
    log.info(f"FSM state successfully set for invitee {invitee.id}")

    # 6. Build the storage key for the inviter. This is the unique identifier
    #    for their state data in the storage (e.g., a specific Redis key).
    inviter_key = StorageKey(
        bot_id=bot.id,
        chat_id=inviter_id,  # For private chat, chat_id is the same as user_id
        user_id=inviter_id,
    )

    await state.storage.set_data(key=inviter_key, data=session_data)
    log.info(f"FSM state successfully set for inviter {inviter_id}")

    # --- END OF FIX ---

    # 7. Send final notifications to both parties
    contacts_kb, _ = await contacts_keyboard(int(inviter_id), redis)
    await bot.send_message(
        inviter_id,
        f"Пользователь @{invitee.username} принял ваше приглашение!"
        f" Нажмите на его контакт, чтобы начать чат.",
        reply_markup=contacts_kb,
    )
    await bot.send_message(
        invitee.id,
        f"Вы приняли приглашение от @{inviter_username}" f" Ожидайте начала сессии.",
    )
    log.info(
        f"Invitation between @{inviter_username} and @{invitee.username}"
        f" is fully resolved."
    )


async def reset_all_chats(user_id: int, redis: Redis):
    """Deletes all stored conversations for the given user."""
    await redis.delete(f"inviter_conversations:{user_id}")
    log.info(f"All chats reset for user {user_id}")


async def initiate_invitation_process(
    inviter: User,
    invitee_id: int,
    bot: Bot,
    redis: Redis,
    # No longer needs FSM state, as we're creating a new invite
) -> str | None:
    """
    Creates a NEW invitation for a specific invitee and sends it.
    This replaces the old logic that looked for existing partners.
    """
    # 1. We need the invitee's username. We can get this with a bot call.
    try:
        invitee_chat = await bot.get_chat(invitee_id)
        invitee_username = invitee_chat.username
        if not invitee_username:
            raise ValueError("Target user does not have a username.")
    except Exception as e:
        log.error(f"Could not get chat for invitee {invitee_id}: {e}")
        raise ValueError(
            f"Не удалось получить информацию о пользователе {invitee_id}."
        ) from e

    # 2. Create a fresh, new invitation and secure_id.
    #    setup_new_invitation stores the inviter's data against the new secure_id.
    secure_id = await setup_new_invitation(inviter.id, inviter.username, redis)
    log.info(
        f"Inviter {inviter.id} is creating a new on-the-fly invitation"
        f" for {invitee_id} with secure_id {secure_id}"
    )

    # 3. Build the confirmation keyboard for the invitee
    builder = InlineKeyboardBuilder()
    builder.row(confirm_button(secure_id), decline_button(secure_id))

    # 4. Send the invitation message to the invitee
    await bot.send_message(
        chat_id=invitee_id,
        text=f"Пользователь @{inviter.username} приглашает вас"
        f" в {settings.LOGO}.\n\n"
        "Принять приглашение?",
        reply_markup=builder.as_markup(),
    )

    return invitee_username


async def show_contact_list_for_inviter(query: CallbackQuery):
    """
    Shows the inviter their list of existing contacts, plus an option for manual input.
    """
    user_id = query.from_user.id

    contacts_kb, num_contacts = await contacts_keyboard(user_id)

    # Use InlineKeyboardBuilder to dynamically add a "Manual Input" button
    builder = InlineKeyboardBuilder.from_markup(contacts_kb)
    builder.row(
        InlineKeyboardButton(
            text="Ручной ввод",
            callback_data=ConversationCallback(role="ie", action="input").pack(),
        )
    )

    if num_contacts > 0:
        text = "Выберите контакт из списка или добавьте новый:"
    else:
        text = (
            "У вас нет активных чатов." " Пригласите собеседника, нажав 'Ручной ввод'."
        )

    await query.message.edit_text(text, reply_markup=builder.as_markup())
    await query.answer()


async def process_invitation_acceptance(
    invitee: User,
    secure_id: str,
    state: FSMContext,  # This is the invitee's FSMContext
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
):
    """
    The core logic after an invitee clicks 'Accept'.
    Performs crypto setup and symmetrically sets FSM state for both users.
    """
    # 1. Get inviter details from Redis
    inviter_id, inviter_username, inviter_public_pem = await get_invitation_details(
        secure_id, redis
    )

    # 2. Perform the cryptographic key exchange
    await setup_conversation_crypto(
        inviter_public_pem=inviter_public_pem,
        inviter_id=inviter_id,
        invitee_id=invitee.id,
        secure_id=secure_id,
        redis=redis,
        pubsub=pubsub,
    )

    # 3. Prepare the shared session data
    session_data = {
        "secure_id": secure_id,
        "inviter_id": inviter_id,
        "inviter_username": inviter_username,
        "invitee_id": invitee.id,
        "invitee_username": invitee.username,
    }

    # 4. Set the state for the invitee (the current user)
    await state.set_data(session_data)
    log.info(f"FSM state successfully set for invitee {invitee.id}")

    # --- THIS IS THE SNIPPET IN ITS CORRECT CONTEXT ---
    # 5. Build the storage key for the other user (the inviter)
    inviter_key = StorageKey(
        bot_id=bot.id,
        chat_id=inviter_id,
        user_id=inviter_id,
    )

    # 6. Use the storage engine from the invitee's context
    # to directly set the data for the inviter
    await state.storage.set_data(key=inviter_key, data=session_data)
    log.info(f"FSM state successfully set for inviter {inviter_id}")

    await store_partner_details(secure_id, invitee, redis)
    # --- END OF SNIPPET CONTEXT ---

    # 7. Send final notifications to both users
    start_button_kb = start_chat_button(invitee.id, invitee.username)
    await bot.send_message(
        inviter_id,
        f"Пользователь @{invitee.username} принял ваше приглашение!"
        f" Нажмите кнопку ниже, чтобы начать.",
        reply_markup=start_button_kb,
    )
    await bot.send_message(
        invitee.id,
        f"✅ Безопасное соединение с @{inviter_username} запрошено.",
    )
    log.info(
        f"Invitation between @{inviter_username} and @{invitee.username}"
        f" is fully resolved."
    )


async def process_invitation_decline(
    invitee: User, secure_id: str, bot: Bot, redis: Redis
):
    """Handles the logic when an invitee declines an invitation."""
    inviter_id, inviter_username, inviter_public_pem = await get_invitation_details(
        secure_id, redis
    )

    msg = (
        f"{settings.LOGO} @{inviter_username}"
        f" приглашение отклонено @{invitee.username}!"
    )

    # Send the inviter a notification with a "Cancel" button to clear their state
    cancel_kb = cancel_button(
        secure_id=secure_id
    )  # Uses our refactored button function
    await bot.send_message(chat_id=inviter_id, text=msg, reply_markup=cancel_kb)
    await bot.send_message(chat_id=invitee.id, text=msg)


async def process_invitation_cancellation(
    inviter: User, secure_id: str, state: FSMContext
):
    """Handles the logic when an inviter cancels a pending invitation."""
    # The core logic is simply to clear the state.
    await state.clear()
    log.info(f"Inviter {inviter.id} cancelled the pending invitation {secure_id}.")


async def get_invitation_details(
    secure_id: str, redis: Redis
) -> tuple[int, str, bytes]:
    """
    Retrieves inviter details (ID, username, public key) from a pending invitation.
    """
    inviter_data = await redis.get(f"{secure_id}:inviter_data")
    if not inviter_data:
        raise ValueError("Invitation is invalid or has expired.")

    inviter_id, inviter_username, public_key_hex = inviter_data.split(":")
    inviter_public_pem = bytes.fromhex(public_key_hex)

    return int(inviter_id), inviter_username, inviter_public_pem


async def setup_conversation_crypto(
    inviter_public_pem: bytes,
    inviter_id: int,
    invitee_id: int,
    secure_id: str,
    redis: Redis,
    pubsub: PubSubService,
):
    """Generates and stores the encrypted symmetric key for the conversation."""
    conv_setup_status = await redis.get(f"{secure_id}:conversation_setup")
    if conv_setup_status != "in_progress":
        raise ValueError("Invalid or already completed conversation setup!")

    symmetric_key = generate_symmetric_key()
    await save_symmetric_key(
        conversation_id=secure_id, symmetric_key=symmetric_key, redis=redis
    )
    encrypted_key = await encrypt_symmetric_key_with_rsa(
        inviter_public_pem, symmetric_key
    )

    await redis.setex(f"{secure_id}:encrypted_key", INVITATION_TTL, encrypted_key.hex())
    await store_inviter_conversation(secure_id, inviter_id, invitee_id, redis)
    await redis.set(f"{secure_id}:conversation_setup", "set_up")
    await pubsub.notify_key_ready(inviter_id, secure_id)


async def resolve_username_to_user(
    username: str, bot: Bot, inviter: User, redis: Redis
) -> dict:
    """Resolves a username string into a user object or a deep link."""
    if not username.startswith("@"):
        return {"success": False, "message": "Неверный формат (@username)."}

    try:
        user = await bot.get_chat(username)
        return {"success": True, "user": user}
    except TelegramBadRequest as e:
        if "chat not found" in str(e):
            deep_link_text = await generate_invitee_deep_link(
                inviter, username, bot, redis
            )
            return {"success": "link_ready", "message": deep_link_text}
    except TelegramAPIError as e:
        return {"success": False, "message": f"Ошибка API: {e}"}


async def process_manual_username_input(
    message: Message, state: FSMContext, bot: Bot, redis: Redis
):
    """
    Orchestrates the entire flow after a user manually enters a username.
    """
    input_text = message.text.strip()
    inviter = message.from_user

    # 1. Resolve the username string to a user object or a deep link
    resolution_result = await resolve_username_to_user(
        input_text, bot, message.from_user, redis
    )

    if not resolution_result["success"]:
        await message.answer(resolution_result["message"])
        return

    # THIS IS THE PART WE ARE FIXING
    if resolution_result["success"] == "link_ready":
        await state.clear()

        # CORRECTED: Call the dedicated UI function to send the message
        await send_invitation_link_message(
            message=message, deep_link_text=resolution_result["message"]
        )

        log.info(f"{inviter.username} prepared a deep link for {input_text}")
        return
    # 2. At this point, we have a valid invitee user object.
    invitee = resolution_result["user"]

    # 3. Find the secure_id associated with this inviter/invitee pair
    # (This logic is from your original on_username_input)
    secure_id = None
    conversations = await redis.smembers(f"inviter_conversations:{inviter.id}")
    for conv in conversations:
        s_id, i_id = conv.split(":")
        if int(i_id) == invitee.id:
            secure_id = s_id
            break

    if not secure_id:
        await message.answer(f"Не удалось найти активный чат с {invitee.username}.")
        return

    # 4. Set up the FSM state for both users
    # --- ✅ THE CORRECT REFACTOR ---

    # 1. Prepare all the new session data in a single Python dictionary.
    new_session_data = {
        "secure_id": secure_id,
        "inviter_id": inviter.id,
        "invitee_id": invitee.id,
        "inviter_username": inviter.username,
        "invitee_username": invitee.username,
    }

    # 2. Set the state. The 'set_data' method automatically overwrites
    #    any old data, so calling 'state.clear()' first is redundant.
    await state.set_data(new_session_data)

    # 5. Notify both parties that the chat is ready
    contacts_kb, _ = await contacts_keyboard(inviter.id, redis)
    await bot.send_message(
        inviter.id,
        f"Нажмите {invitee.username} для начала {settings.LOGO}!",
        reply_markup=contacts_kb,
    )
    await bot.send_message(
        invitee.id,
        f"Ожидаем начала {settings.LOGO}а с {inviter.username}.",
    )
    log.info(f"{settings.LOGO} @{inviter.username}/@{invitee.username} запущен.")


async def present_invitation_to_invitee(
    invitee: User, secure_id: str, bot: Bot, redis: Redis
):
    """
    Shows the 'Accept/Decline' keyboard to an invitee who has used a deep link.
    """
    try:
        # We still need to get the inviter's name to show in the message
        inviter_id, inviter_username, _ = await get_invitation_details(secure_id, redis)
    except ValueError:
        await bot.send_message(
            invitee.id, "Эта ссылка-приглашение недействительна или истекла."
        )
        return

    # Prevent self-invites early
    if invitee.id == inviter_id:
        await bot.send_message(
            invitee.id, "Вы не можете использовать собственное приглашение."
        )
        return

    # Build the keyboard using our refactored button functions
    builder = InlineKeyboardBuilder()
    builder.row(
        confirm_button(secure_id),  # The value is the secure_id
        decline_button(secure_id),
    )

    # Send the confirmation message
    await bot.send_message(
        chat_id=invitee.id,
        text=f"Пользователь @{inviter_username} приглашает вас в {settings.LOGO}.\n\n"
        "Принять приглашение?",
        reply_markup=builder.as_markup(),
    )


async def store_partner_details(secure_id: str, partner: User, redis: Redis):
    """
    Stores a user's details (ID, username, etc.) in Redis against a secure_id.
    This makes the user discoverable as a "contact" or "partner" later.
    """
    partner_data = {
        "invitee_id": partner.id,
        "username": partner.username or f"User_{partner.id}",
        "first_name": partner.first_name,
        "last_name": partner.last_name or "",
        "secure_id": secure_id,
    }

    # Store the JSON data with a long TTL
    await redis.setex(
        f"conversation_invitee:{secure_id}", PARTNER_DATA_TTL, json.dumps(partner_data)
    )
    log.info(
        f"Stored partner details for user {partner.id} against secure_id {secure_id}"
    )


async def start_direct_chat_session(
    inviter: User,
    invitee_id: int,
    inviter_state: FSMContext,  # <-- CRITICAL: Pass the inviter's own FSMContext
    bot: Bot,
    redis: Redis,
    pubsub: PubSubService,
):
    """
    Directly establishes a secure session with a known partner.

    This refactored version correctly uses the provided FSMContext to
    symmetrically set the state for both participants without creating
    new FSMContext objects manually.

    Args:
        inviter: The User object of the person initiating the chat.
        invitee_id: The ID of the person being invited.
        inviter_state: The FSMContext of the inviter.
        bot: The Bot instance.
        redis: The Redis client instance.
        pubsub: The PubSub service instance.
    """
    # 1. Get invitee details for notifications
    try:
        invitee_chat = await bot.get_chat(invitee_id)
        invitee_username = invitee_chat.username
        if not invitee_username:
            raise ValueError("Target user does not have a username.")
    except Exception as e:
        raise ValueError(
            f"Не удалось получить информацию о пользователе {invitee_id}."
        ) from e

    # 2. Create a new secure_id and get the inviter's public key for the exchange
    secure_id = await setup_new_invitation(inviter.id, inviter.username, redis)
    inviter_id, _, inviter_public_pem = await get_invitation_details(secure_id, redis)

    # 3. Perform the cryptographic setup (invitee generates and sends the AES key)
    await setup_conversation_crypto(
        inviter_public_pem, inviter_id, invitee_id, secure_id, redis, pubsub
    )

    # 4. Prepare the shared session data
    session_data = {
        "secure_id": secure_id,
        "inviter_id": inviter_id,
        "inviter_username": inviter.username,
        "invitee_id": invitee_id,
        "invitee_username": invitee_username,
    }

    # 5. Set the state for the inviter using their provided context
    await inviter_state.set_data(session_data)
    log.info(f"FSM state successfully set for inviter {inviter_id}")

    # 6. Build the unique storage key for the invitee
    invitee_key = StorageKey(
        bot_id=bot.id,
        chat_id=invitee_id,
        user_id=invitee_id,
    )

    # 7. Use the inviter's storage engine to directly set the data for the invitee's key
    await inviter_state.storage.set_data(key=invitee_key, data=session_data)
    log.info(f"FSM state successfully set for invitee {invitee_id}")

    # 8. Send the final confirmation message to both users
    final_message = "✅ Безопасное соединение установлено. Вы можете начать общение."
    await bot.send_message(inviter_id, final_message)
    await bot.send_message(invitee_id, final_message)
    log.info(
        f"Direct chat between @{inviter.username} and @{invitee_username} established."
    )
