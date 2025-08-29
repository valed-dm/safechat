from bot.services.pubsub_service import PubSubService


async def start_key_exchange_listener(user_id: int, pubsub: PubSubService):
    """
    Starts the single, self-managing background key exchange listener for a user.
    """
    pubsub.start_listener_for_user(user_id)
