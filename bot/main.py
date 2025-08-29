import asyncio
import sys

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from bot.core.config import settings
from bot.core.logging_setup import log
from bot.core.logging_setup import setup_logging
from bot.handlers import router as main_router
from bot.middlewares.conversation_middleware import ConversationDataMiddleware
from bot.services.pubsub_service import PubSubService


async def on_startup(dispatcher: Dispatcher):
    """Tasks to execute on bot startup."""
    redis: Redis = dispatcher["redis"]
    log.info("Checking connection to Redis...")
    try:
        await redis.ping()
        log.info("Successfully connected to Redis.")
    except ConnectionError as e:
        log.critical("Fatal error: Could not connect to Redis on startup: {}", e)
        sys.exit("Terminating due to Redis connection failure.")
    except Exception as e:
        log.error("An unexpected error occurred on startup: {}", e)

    log.info("Starting {} bot...", settings.LOGO)


async def on_shutdown(dispatcher: Dispatcher):
    """Tasks to execute on bot shutdown."""
    log.info("Shutting down...")
    redis: Redis = dispatcher["redis"]
    await redis.aclose()
    log.info("Redis connection closed.")

    bot: Bot = dispatcher["bot"]
    await bot.session.close()
    log.info("Bot session closed.")
    log.info("Polling finished.")


async def main_async():
    """SecureTalk Bot entry point"""
    setup_logging()
    log.info("Starting bot initialization...")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
    )
    pubsub_service = PubSubService(redis_client)

    dp = Dispatcher(
        storage=MemoryStorage(),
        bot=bot,
        redis=redis_client,
        pubsub=pubsub_service,
    )

    dp.message.outer_middleware.register(ConversationDataMiddleware(redis_client))

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(main_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main_async())
