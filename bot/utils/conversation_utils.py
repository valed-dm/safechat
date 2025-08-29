from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.types import Message
from redis import Redis

from bot.core.config import settings
from bot.core.logging_setup import log
from bot.keyboards.button_abort import abort_button
from bot.keyboards.button_decrypt import decrypt_button
from bot.utils.crypto_utils import decrypt_message_with_aes
from bot.utils.crypto_utils import encrypt_message_with_aes
from bot.utils.crypto_utils import retrieve_symmetric_key
from bot.utils.redis_cache import cache_large_data
from bot.utils.redis_cache import retrieve_cached_data


async def propose_abort(
    message: Message,
    bot: Bot,
    secure_id: str,
    recipient_id: int,
    sender_prefix: str,
    recipient_prefix: str,
):
    """Sends an abort confirmation to both participants using the new factories."""
    recipient_btn = abort_button(role=recipient_prefix, secure_id=secure_id)
    sender_btn = abort_button(role=sender_prefix, secure_id=secure_id)

    abort_message = f"Прервать {settings.LOGO}?"
    await bot.send_message(
        chat_id=recipient_id, text=abort_message, reply_markup=recipient_btn
    )
    await message.reply(text=abort_message, reply_markup=sender_btn)


async def encrypt_and_relay_message(
    message: Message,
    bot: Bot,
    secure_id: str,
    recipient_id: int,
    recipient_prefix: str,
    redis: Redis,
):
    """
    Encrypts a message and sends it to the recipient with a refactored decrypt button.
    """
    symmetric_key = await retrieve_symmetric_key(conversation_id=secure_id, redis=redis)
    sender = message.from_user

    try:
        encrypted_text = await encrypt_message_with_aes(
            key=symmetric_key, plaintext=message.text
        )
        encrypted_hex = encrypted_text.hex()

        # 1. Store the large encrypted_hex in Redis and get a short key
        cache_key = await cache_large_data(encrypted_hex, redis)

        decrypt_btn = decrypt_button(role=recipient_prefix, cache_key=cache_key)

        recipient_chat = await bot.get_chat(recipient_id)

        await bot.send_message(
            chat_id=recipient_id,
            text=f"@{sender.username} 🔑{encrypted_hex[:10]}..",
            reply_markup=decrypt_btn,
        )
        await message.reply(
            f"@{sender.username} закрытое сообщение "
            f"@{recipient_chat.username} передано успешно!",
        )
    except Exception as e:
        msg = f"❌ Ошибка сообщения {settings.LOGO}: {e}"
        await message.reply(msg)
        log.exception(msg)


async def abort_conversation_state(state: FSMContext) -> tuple[str, str]:
    """
    Aborts the secure talk by clearing the FSM state and returns participant usernames.
    """
    # --- ✅ REFACTORED STATE USAGE ---
    fsm_data = await state.get_data()
    secure_id = fsm_data.get("secure_id")

    if not secure_id:
        raise ValueError("No active conversation to abort.")

    invitee_username = fsm_data.get("invitee_username")
    inviter_username = fsm_data.get("inviter_username")

    await state.clear()

    log.info(
        f"State cleared for conversation between"
        f" @{inviter_username} and @{invitee_username}."
    )

    return inviter_username, invitee_username


async def decrypt_and_show_message(
    query: CallbackQuery,
    state: FSMContext,
    redis: Redis,
    cache_key: str,
):
    """
    Retrieves the symmetric key, decrypts the message, and displays it in an alert.
    """
    # --- ✅ REFACTORED STATE USAGE ---
    fsm_data = await state.get_data()
    secure_id = fsm_data.get("secure_id")

    if not secure_id:
        raise ValueError(
            "Cannot decrypt: no active secure session found in your state."
        )

    # Retrieve the symmetric key from our new Redis-based storage
    symmetric_key_bytes = await retrieve_symmetric_key(secure_id, redis)
    if not symmetric_key_bytes:
        raise ValueError("Cannot decrypt: symmetric key not found for this session.")

    # Get sender username from the FSM data dictionary
    inviter_id = fsm_data.get("inviter_id")
    invitee_username = fsm_data.get("invitee_username")
    inviter_username = fsm_data.get("inviter_username")

    if query.from_user.id == inviter_id:
        sender_username = invitee_username
    else:
        sender_username = inviter_username
    # --- END OF REFACTOR ---

    # 4. Convert hex data from the callback to bytes
    encrypted_hex = await retrieve_cached_data(cache_key, redis)
    if not encrypted_hex:
        raise ValueError(
            "Сообщение истекло или недействительно."
            " (Message has expired or is invalid.)"
        )
    try:
        iv_ciphertext_bytes = bytes.fromhex(encrypted_hex)
    except ValueError as error:
        raise ValueError("Invalid format: encrypted data is not valid hex.") from error

    # 5. Call the core decryption utility
    decrypted_text = await decrypt_message_with_aes(
        key=symmetric_key_bytes, iv_ciphertext=iv_ciphertext_bytes
    )

    # 6. Format the final message and show it as a pop-up alert
    msg = f"@{sender_username}: {decrypted_text}"
    await query.answer(text=msg, show_alert=True)
    log.info(
        f"User {query.from_user.id}" f" decrypted a message from @{sender_username}."
    )
