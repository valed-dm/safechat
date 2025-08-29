from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


class IsInConversationFilter(Filter):
    """
    Filter to check if a user is in a state with a valid 'secure_id'.
    """

    async def __call__(self, message: Message, state: FSMContext) -> bool:
        user_data = await state.get_data()
        return user_data.get("secure_id") is not None
