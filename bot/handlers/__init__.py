from aiogram import Router

from . import callback_handlers
from . import commands
from . import inline_handlers
from . import user_messages


router = Router(name="main-handlers-router")

router.include_router(commands.router)
router.include_router(callback_handlers.router)
router.include_router(inline_handlers.router)
router.include_router(user_messages.router)
