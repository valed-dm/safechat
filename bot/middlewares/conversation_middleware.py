from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Dict

from aiogram import BaseMiddleware
from aiogram.types import Message
from redis.asyncio import Redis


class ConversationDataMiddleware(BaseMiddleware):
    """
    This middleware prepares data for handlers that operate within a secure talk.
    It identifies the recipient and injects their ID and other details into the handler.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # We need the state from the dispatcher data
        state = data.get("state")
        if not state:
            return await handler(event, data)

        # --- ✅ REFACTORED STATE USAGE ---
        # 1. Read the data directly from the state
        fsm_data = await state.get_data()

        # 2. Check for the existence of our session key
        secure_id = fsm_data.get("secure_id")
        if not secure_id:
            return await handler(event, data)

        # 3. Use the data directly from the dictionary
        sender_id = event.from_user.id
        inviter_id = int(fsm_data.get("inviter_id"))
        invitee_id = int(fsm_data.get("invitee_id"))

        # --- END OF REFACTOR ---

        # Check if the sender is part of the conversation
        if sender_id not in (inviter_id, invitee_id):
            # In a middleware, we can choose to stop processing or just not add data.
            # We can even send a message, though it's often better handled by a filter.
            return await handler(event, data)

        # Determine the recipient
        if sender_id == invitee_id:
            recipient_id = inviter_id
            recipient_role = "inviter"
            recipient_prefix = "ir"
            sender_prefix = "ie"
        else:
            recipient_id = invitee_id
            recipient_role = "invitee"
            recipient_prefix = "ie"
            sender_prefix = "ir"

        # Injecting the data into the handler's scope.
        # Now handlers can simply ask for 'recipient_id' in their signature!
        data["recipient_id"] = recipient_id
        data["recipient_role"] = recipient_role
        data["recipient_prefix"] = recipient_prefix
        data["sender_prefix"] = sender_prefix
        data["secure_id"] = secure_id

        return await handler(event, data)
