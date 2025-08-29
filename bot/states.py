from aiogram.fsm.state import State
from aiogram.fsm.state import StatesGroup


class ConversationStates(StatesGroup):
    """
    Defines the states for the conversation setup process.
    """

    entering_username = State()

    # If you have more states in the future, you can add them here.
    # For example:
    # changing_settings = State()
    # awaiting_confirmation = State()
