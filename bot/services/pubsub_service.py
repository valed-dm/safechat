import asyncio
import json

from redis.asyncio import Redis

from bot.core.logging_setup import log
from bot.utils.crypto_utils import decrypt_symmetric_key_with_rsa
from bot.utils.crypto_utils import save_symmetric_key
from bot.utils.inviter_utils import get_decrypted_private_key


class PubSubService:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.notification_tasks = {}

    async def _notify(self, channel: str, event: str, data: str):
        """Publishes a standardized message to a channel."""
        message = {"event": event, "data": data}
        await self.redis.publish(channel, json.dumps(message))

    async def notify_key_ready(self, inviter_id: int, secure_id: str):
        await self._notify(
            f"conversation:notifications:{inviter_id}", "key_ready", secure_id
        )

    async def notify_key_received(self, inviter_id: int, secure_id: str):
        await self._notify(
            f"conversation:notifications:{inviter_id}", "key_received", secure_id
        )

    async def _process_key_ready_event(self, secure_id: str, inviter_id: int):
        """The logic for when the inviter receives the encrypted AES key."""
        encrypted_key_hex = await self.redis.get(f"{secure_id}:encrypted_key")
        if not encrypted_key_hex:
            log.error(f"Encrypted key for {secure_id} not found!")
            return

        private_key_pem = await get_decrypted_private_key(inviter_id, self.redis)
        if not private_key_pem:
            log.error(f"Could not retrieve private key for inviter {inviter_id}")
            return

        symmetric_key = await decrypt_symmetric_key_with_rsa(
            private_key_pem=private_key_pem,
            encrypted_key=bytes.fromhex(encrypted_key_hex),
        )

        await save_symmetric_key(secure_id, symmetric_key, self.redis)
        log.info(
            f"Inviter {inviter_id} successfully stored symmetric key for {secure_id}"
        )
        await self.notify_key_received(inviter_id, secure_id)

    async def _sym_notification_listener(self, user_id: int):
        """The core background task that listens on a user's notification channel."""
        channel_name = f"conversation:notifications:{user_id}"
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel_name)
        log.info(f"Started Pub/Sub listener for user {user_id} on {channel_name}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    payload = json.loads(message["data"])
                    event = payload.get("event")
                    data = payload.get("data")

                    if event == "key_ready":
                        await self._process_key_ready_event(
                            secure_id=data, inviter_id=user_id
                        )
                    elif event == "key_received":
                        log.info(
                            f"Key exchange confirmation received for user {user_id}."
                            f" Stopping listener."
                        )
                        break  # Exit the loop, task will end
        except Exception as e:
            log.exception(f"Error in listener for user {user_id}: {e}")
        finally:
            log.info(f"Stopping Pub/Sub listener for user {user_id}")
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    def start_listener_for_user(self, user_id: int):
        """Starts a new background listener for a user if one isn't running."""
        if user_id in self.notification_tasks:
            log.warning(f"Listener task for user {user_id} is already running.")
            return

        task = asyncio.create_task(self._sym_notification_listener(user_id))
        self.notification_tasks[user_id] = task
        # This ensures that when a task finishes (or fails), it's removed from the dict
        task.add_done_callback(lambda t: self.notification_tasks.pop(user_id, None))
