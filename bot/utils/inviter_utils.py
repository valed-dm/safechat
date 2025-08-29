import json
from uuid import uuid4

from redis.asyncio import Redis

from bot.core.logging_setup import log
from bot.utils.crypto_utils import decrypt_private_key
from bot.utils.crypto_utils import encrypt_private_key
from bot.utils.crypto_utils import generate_rsa_keypair


# --- Refactored Redis-based Key Storage ---


async def store_rsa_keys(
    inviter_id: int, private_pem: bytes, public_pem: bytes, redis: Redis
):
    """Stores the inviter's RSA keys securely in Redis."""
    # We'll use a simple, consistent passphrase for encryption/decryption
    passphrase = f"secure_talk_pass_{inviter_id}"
    encrypted_private_pem = await encrypt_private_key(private_pem, passphrase)

    # Store keys in a Redis hash for easy access
    key_storage_key = f"user:{inviter_id}:keys"
    await redis.hset(
        key_storage_key,
        mapping={
            "public_pem": public_pem.decode("utf-8"),
            "encrypted_private_pem": encrypted_private_pem.hex(),
        },
    )
    log.info(f"Stored new RSA key pair in Redis for user {inviter_id}")


async def get_public_key(inviter_id: int, redis: Redis) -> bytes | None:
    """Retrieves the public key for a user from Redis."""
    public_pem_str = await redis.hget(f"user:{inviter_id}:keys", "public_pem")
    return public_pem_str.encode("utf-8") if public_pem_str else None


async def get_decrypted_private_key(inviter_id: int, redis: Redis) -> bytes | None:
    """Retrieves and decrypts the private key for a user from Redis."""
    encrypted_pem_hex = await redis.hget(
        f"user:{inviter_id}:keys", "encrypted_private_pem"
    )
    if not encrypted_pem_hex:
        return None

    passphrase = f"secure_talk_pass_{inviter_id}"
    encrypted_pem = bytes.fromhex(encrypted_pem_hex)
    return await decrypt_private_key(encrypted_pem, passphrase)


# --- Refactored Conversation Partner Logic ---


async def store_inviter_conversation(
    secure_id: str, inviter_id: int, invitee_id: int, redis: Redis
):
    """Saves a single conversation pair for an inviter."""
    await redis.sadd(f"inviter_conversations:{inviter_id}", f"{secure_id}:{invitee_id}")


async def get_inviter_partners(inviter_id: int, redis: Redis) -> list[dict]:
    """Retrieves and cleans the list of an inviter's partners."""
    conv_key = f"inviter_conversations:{inviter_id}"
    conversations = await redis.smembers(conv_key)
    partners = []

    for conversation in conversations:
        secure_id, invitee_id = conversation.split(":")
        invitee_data_json = await redis.get(f"conversation_invitee:{secure_id}")

        if invitee_data_json:
            partners.append(json.loads(invitee_data_json))
        else:
            # Auto-cleanup of stale conversation links
            log.warning(
                f"Cleaning up stale conversation {secure_id} for inviter {inviter_id}"
            )
            await redis.srem(conv_key, conversation)

    return partners


# REFACTORED from 'initialize_inviter_workflow'
async def initialize_inviter_workflow(inviter_id: int, redis: Redis):
    """
    Ensures an inviter has an RSA key pair, generating one if it doesn't exist.
    """
    # Check if keys already exist to avoid generating new ones on every /start
    if not await redis.exists(f"user:{inviter_id}:keys"):
        log.info(f"No RSA keys found for user {inviter_id}. Generating a new pair.")
        private_pem, public_pem = await generate_rsa_keypair()
        await store_rsa_keys(inviter_id, private_pem, public_pem, redis)
    else:
        log.info(f"Existing RSA keys found for user {inviter_id}.")


async def setup_new_invitation(
    inviter_id: int,
    inviter_username: str,
    redis: Redis,
    ttl=3600,
) -> str:
    """
    Prepares a new invitation by creating a secure_id and storing inviter data.
    """
    secure_id = str(uuid4())

    public_pem = await get_public_key(inviter_id, redis)
    if not public_pem:
        raise ValueError(
            f"Could not find a public key for inviter {inviter_id}."
            f" Please /start again."
        )

    # Store the data needed for an invitee to resolve the invitation
    await redis.setex(
        f"{secure_id}:inviter_data",
        ttl,
        f"{inviter_id}:{inviter_username}:{public_pem.hex()}",
    )
    await redis.setex(f"{secure_id}:conversation_setup", ttl, "in_progress")

    log.info(
        f"Inviter {inviter_id} created a new invitation with secure_id {secure_id}"
    )
    return secure_id
