# import json
#
# from aiogram import Bot
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.storage.base import StorageKey
# from aiogram.types import Chat
# from aiogram.types import User
# from aiogram.utils.keyboard import InlineKeyboardBuilder
# from redis.asyncio import Redis
#
# from bot.core.config import settings
# from bot.core.logging_setup import log
# from bot.keyboards.button_cancel import cancel_button
# from bot.keyboards.invitation_buttons import confirm_button
# from bot.keyboards.invitation_buttons import decline_button
# from bot.keyboards.invitation_buttons import start_chat_button
# from bot.services.pubsub_service import PubSubService
# from bot.utils.crypto_utils import encrypt_symmetric_key_with_rsa
# from bot.utils.crypto_utils import generate_symmetric_key
# from bot.utils.crypto_utils import save_symmetric_key
# from bot.utils.invitation_utils import get_invitation_details
# from bot.utils.inviter_utils import store_inviter_conversation
#
#
# PARTNER_DATA_TTL = 86400 * 30  # 30 days
# INVITATION_TTL = 3600
#
# # --- Class 1: The Pending Invitation ---
#
#
# class Invitation:
#     """Represents a pending invitation, handling validation and presentation."""
#
#     def __init__(self, secure_id: str, redis: Redis):
#         self.secure_id = secure_id
#         self.redis = redis
#         self.inviter_id: int | None = None
#         self.inviter_username: str | None = None
#         self._is_loaded = False
#
#     async def _load(self):
#         if self._is_loaded:
#             return
#         try:
#             self.inviter_id, self.inviter_username, _ = await get_invitation_details(
#                 self.secure_id, self.redis
#             )
#             self._is_loaded = True
#         except ValueError:
#             self._is_loaded = False
#
#     @property
#     async def is_valid(self) -> bool:
#         await self._load()
#         return self._is_loaded
#
#     async def is_self_invite(self, invitee: User) -> bool:
#         await self._load()
#         return self.inviter_id == invitee.id
#
#     async def present_to_invitee(self, invitee: User, bot: Bot):
#         """Shows the 'Accept/Decline' keyboard to the invitee."""
#         builder = InlineKeyboardBuilder()
#         builder.row(confirm_button(self.secure_id), decline_button(self.secure_id))
#         await bot.send_message(
#             chat_id=invitee.id,
#             text=f"Пользователь @{self.inviter_username}
#             приглашает вас в {settings.LOGO}.\n\nПринять приглашение?",
#             reply_markup=builder.as_markup(),
#         )
#
#     async def decline(self, invitee: User, bot: Bot):
#         """Notifies the inviter that the invitation was declined."""
#         await self._load()
#         msg = f"{settings.LOGO} @{self.inviter_username}
#         приглашение отклонено @{invitee.username}!"
#         cancel_kb = cancel_button(self.secure_id)
#         await bot.send_message(
#             chat_id=self.inviter_id, text=msg, reply_markup=cancel_kb
#         )
#         await bot.send_message(chat_id=invitee.id, text=msg)
#
#
# # --- Class 2: The Active Secure Session ---
#
#
# class SecureSession:
#     """Represents an active, established secure chat session."""
#
#     def __init__(self, secure_id: str, bot: Bot, redis: Redis, pubsub: PubSubService):
#         self.secure_id = secure_id
#         self.bot = bot
#         self.redis = redis
#         self.pubsub = pubsub
#         self.inviter: Chat | None = None
#         self.invitee: User | None = None
#
#     async def establish(
#     self, inviter: User, invitee: User, invitee_state: FSMContext
#     ):
#         """
#         The main method to establish the session: performs crypto,
#         sets state, and notifies users.
#         """
#         self.inviter = inviter
#         self.invitee = invitee
#
#         await self._perform_crypto_setup()
#         await self._set_symmetric_fsm_state(invitee_state)
#         await self._store_partner_details()
#         await self._send_final_notifications()
#         log.info(
#             f"Session {self.secure_id} between @{self.inviter.username}
#             and @{self.invitee.username} is fully resolved."
#         )
#
#     async def _perform_crypto_setup(self):
#         _, _, inviter_public_pem = await get_invitation_details(
#             self.secure_id, self.redis
#         )
#         symmetric_key = generate_symmetric_key()
#         await save_symmetric_key(self.secure_id, symmetric_key, self.redis)
#         encrypted_key = await encrypt_symmetric_key_with_rsa(
#             inviter_public_pem, symmetric_key
#         )
#
#         await self.redis.setex(
#             f"{self.secure_id}:encrypted_key", INVITATION_TTL, encrypted_key.hex()
#         )
#         await store_inviter_conversation(
#             self.secure_id, self.inviter.id, self.invitee.id, self.redis
#         )
#         await self.redis.set(f"{self.secure_id}:conversation_setup", "set_up")
#         await self.pubsub.notify_key_ready(self.inviter.id, self.secure_id)
#
#     async def _set_symmetric_fsm_state(self, invitee_state: FSMContext):
#         session_data = {
#             "secure_id": self.secure_id,
#             "inviter_id": self.inviter.id,
#             "inviter_username": self.inviter.username,
#             "invitee_id": self.invitee.id,
#             "invitee_username": self.invitee.username,
#         }
#         await invitee_state.set_data(session_data)
#
#         inviter_key = StorageKey(
#             bot_id=self.bot.id, chat_id=self.inviter.id, user_id=self.inviter.id
#         )
#         await invitee_state.storage.set_data(key=inviter_key, data=session_data)
#         log.info(
#             f"Symmetric FSM state set for users {self.inviter.id}
#             and {self.invitee.id}"
#         )
#
#     async def _store_partner_details(self):
#         partner_data = {
#             "invitee_id": self.invitee.id,
#             "username": self.invitee.username or f"User_{self.invitee.id}",
#             "first_name": self.invitee.first_name,
#             "last_name": self.invitee.last_name or "",
#             "secure_id": self.secure_id,
#         }
#         await self.redis.setex(
#             f"conversation_invitee:{self.secure_id}",
#             PARTNER_DATA_TTL,
#             json.dumps(partner_data),
#         )
#
#     async def _send_final_notifications(self):
#         start_button_kb = start_chat_button(self.invitee.id, self.invitee.username)
#         await self.bot.send_message(
#             self.inviter.id,
#             f"Пользователь @{self.invitee.username} принял ваше приглашение!
#             Нажмите кнопку ниже, чтобы начать.",
#             reply_markup=start_button_kb,
#         )
#         await self.bot.send_message(
#             self.invitee.id,
#             f"Вы приняли приглашение от @{self.inviter.username}.
#             Ожидайте начала сессии.",
#         )
