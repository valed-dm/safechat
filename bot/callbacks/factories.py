from aiogram.filters.callback_data import CallbackData


class InvitationCallback(CallbackData, prefix="invite"):
    """
    Callback data for responding to an invitation.
    - action: 'accept', 'decline'
    - value: The secure_id of the invitation
    """

    action: str
    value: str


class SecureActionCallback(CallbackData, prefix="sec"):
    """
    Callback data for secure actions like decrypting or aborting.
    - role: 'ir' (inviter) or 'ie' (invitee)
    - action: 'decrypt', 'abort'
    - value: The data (encrypted hex) or the secure_id
    """

    role: str
    action: str
    value: str


class ConversationCallback(CallbackData, prefix="conv"):
    """
    Callback data for general conversation actions.
    - role: 'ir', 'ie'
    - action: 'prepare', 'invite', 'cancel', 'reset', 'input', 'start'
    - value: Optional value, e.g., a user ID
    """

    role: str
    action: str
    value: str | None = None
