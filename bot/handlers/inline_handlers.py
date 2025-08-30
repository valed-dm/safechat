from aiogram import Bot
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import ChosenInlineResult
from aiogram.types import InlineQuery
from aiogram.types import InlineQueryResultArticle
from aiogram.types import InputTextMessageContent
from redis.asyncio import Redis

from bot.core.logging_setup import log
from bot.keyboards.button_decrypt import decrypt_button
from bot.utils.crypto_utils import encrypt_message_with_aes
from bot.utils.crypto_utils import retrieve_symmetric_key
from bot.utils.redis_cache import cache_large_data
from bot.utils.redis_cache import retrieve_cached_data


router = Router(name="inline-handlers")


@router.inline_query()
async def handle_secure_inline_input(
    inline_query: InlineQuery,
    state: FSMContext,
    redis: Redis,
):
    """Handles inline queries for encrypting messages on the fly."""
    # 1. Get the user's current state to find their conversation partner
    # --- ✅ ADD DEBUG LOGGING ---
    log.debug(
        f"Received inline query from user {inline_query.from_user.id} with text:"
        f" '{inline_query.query}'"
    )
    fsm_data = await state.get_data()
    log.debug(f"User's current FSM state: {fsm_data}")
    # --- END DEBUG LOGGING ---
    secure_id = fsm_data.get("secure_id")
    inviter_id = fsm_data.get("inviter_id")
    invitee_id = fsm_data.get("invitee_id")

    # If the user is not in a secure session, do nothing.
    if not all([secure_id]):
        log.warning(
            f"User {inline_query.from_user.id} tried to use inline mode"
            f" without a valid session state. Aborting."
        )
        return

    # 2. Determine the recipient
    # --- ✅ REFINED RECIPIENT LOGIC ---
    if inline_query.from_user.id == inviter_id:
        recipient_id = invitee_id
        recipient_prefix = "ie"
        partner_username = fsm_data.get("invitee_username")
    else:
        recipient_id = inviter_id
        recipient_prefix = "ir"
        partner_username = fsm_data.get("inviter_username")
    # --- END REFINEMENT ---

    # 3. Get the plaintext message the user has typed
    plaintext = inline_query.query
    if not plaintext:  # Don't do anything if the query is empty
        return

    # 4. Encrypt the plaintext
    try:
        symmetric_key = await retrieve_symmetric_key(secure_id, redis)
        if not symmetric_key:
            raise ValueError("Symmetric key not found for this session.")

        encrypted_text = await encrypt_message_with_aes(symmetric_key, plaintext)
        encrypted_hex = encrypted_text.hex()

        # 5. Cache the large encrypted data and get a short key
        cache_key = await cache_large_data(encrypted_hex, redis)

        # 6. Create the "Decrypt" button for the final message
        decrypt_button(role=recipient_prefix, cache_key=cache_key)

        # 7. Create the inline query result
        result_id = f"{cache_key}:{recipient_id}:{recipient_prefix}"
        title = "Нажмите, чтобы зашифровать и подготовить сообщение"
        description = f"Будет зашифровано: {plaintext[:50]}..."

        # This is the message that will actually be sent
        final_message_content = InputTextMessageContent(
            message_text=f"✅ Ваше сообщение для @{partner_username}"
                         f" зашифровано и направлено получателю."
        )

        result = InlineQueryResultArticle(
            id=result_id,
            title=title,
            description=description,
            input_message_content=final_message_content,
        )

        # Answer the inline query with our single, encrypted result
        await inline_query.answer([result], is_personal=True, cache_time=0)

    except Exception as e:
        # If something goes wrong, we can show an error result
        error_result = InlineQueryResultArticle(
            id="error",
            title="Ошибка шифрования",
            description=str(e),
            input_message_content=InputTextMessageContent(
                message_text=f"Не удалось зашифровать: {e}"
            ),
        )
        await inline_query.answer([error_result], is_personal=True, cache_time=0)


@router.chosen_inline_result()
async def handle_chosen_result_and_relay(
    chosen_result: ChosenInlineResult,
    bot: Bot,
    redis: Redis,
):
    sender = chosen_result.from_user
    try:
        cache_key, recipient_id_str, recipient_prefix = chosen_result.result_id.split(
            ":", 2,
        )
        recipient_id = int(recipient_id_str)
    except (ValueError, IndexError):
        return

    encrypted_hex = await retrieve_cached_data(cache_key, redis)
    if not encrypted_hex:
        # ... error message to sender
        return

    # 4. Create the "Decrypt" button for the recipient
    decrypt_kb = decrypt_button(role=recipient_prefix, cache_key=cache_key)

    # 5. Send the encrypted message to the INTENDED RECIPIENT
    await bot.send_message(
        chat_id=recipient_id,
        text=f"🔑 Вам новое зашифрованное сообщение от"
             f" @{sender.username} ({encrypted_hex[:10]}...)",
        reply_markup=decrypt_kb
    )
