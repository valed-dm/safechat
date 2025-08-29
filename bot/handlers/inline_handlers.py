# from aiogram import Bot
# from aiogram import Router
# from aiogram.fsm.context import FSMContext
# from aiogram.types import InlineQuery
# from aiogram.types import InlineQueryResultArticle
# from aiogram.types import InputTextMessageContent
# from redis.asyncio import Redis
#
# from bot.keyboards.button_decrypt import decrypt_button
# from bot.utils.crypto_utils import retrieve_symmetric_key, encrypt_message_with_aes
# from bot.utils.redis_cache import cache_large_data
#
#
# router = Router(name="inline-handlers")
#
#
# @router.inline_query()
# async def handle_secure_inline_input(
#     inline_query: InlineQuery,
#     state: FSMContext,
#     redis: Redis,
#     bot: Bot,
# ):
#     """
#     Handles inline queries for encrypting messages on the fly.
#     """
#     # 1. Get the user's current state to find their conversation partner
#     fsm_data = await state.get_data()
#     secure_id = fsm_data.get("secure_id")
#     inviter_id = fsm_data.get("inviter_id")
#     fsm_data.get("invitee_id")
#
#     # If the user is not in a secure session, do nothing.
#     if not secure_id:
#         return
#
#     # 2. Determine the recipient
#     if inline_query.from_user.id == inviter_id:
#         recipient_prefix = "ie"  # The invitee will decrypt
#     else:
#         recipient_prefix = "ir"  # The inviter will decrypt
#
#     # 3. Get the plaintext message the user has typed
#     plaintext = inline_query.query
#     if not plaintext:  # Don't do anything if the query is empty
#         return
#
#     # 4. Encrypt the plaintext
#     try:
#         symmetric_key = await retrieve_symmetric_key(secure_id, redis)
#         if not symmetric_key:
#             raise ValueError("Symmetric key not found for this session.")
#
#         encrypted_text = await encrypt_message_with_aes(symmetric_key, plaintext)
#         encrypted_hex = encrypted_text.hex()
#
#         # 5. Cache the large encrypted data and get a short key
#         cache_key = await cache_large_data(encrypted_hex, redis)
#
#         # 6. Create the "Decrypt" button for the final message
#         decrypt_kb = decrypt_button(role=recipient_prefix, cache_key=cache_key)
#
#         # 7. Create the inline query result
#         result_id = str(hash(plaintext))  # A unique ID for this result
#         title = "Нажмите, чтобы отправить зашифрованное сообщение"
#         description = f"Сообщение: {plaintext[:50]}..."
#
#         # This is the message that will actually be sent
#         final_message_content = InputTextMessageContent(
#             message_text=f"🔑 Зашифрованное сообщение ({encrypted_hex[:10]}...)"
#         )
#
#         result = InlineQueryResultArticle(
#             id=result_id,
#             title=title,
#             description=description,
#             input_message_content=final_message_content,
#             reply_markup=decrypt_kb,
#         )
#
#         # Answer the inline query with our single, encrypted result
#         await inline_query.answer([result], is_personal=True, cache_time=0)
#
#     except Exception as e:
#         # If something goes wrong, we can show an error result
#         error_result = InlineQueryResultArticle(
#             id="error",
#             title="Ошибка шифрования",
#             description=str(e),
#             input_message_content=InputTextMessageContent(
#                 message_text=f"Не удалось зашифровать: {e}"
#             ),
#         )
#         await inline_query.answer([error_result], is_personal=True, cache_time=0)
