from datetime import datetime, timedelta
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config.store import get_telegram_api_credentials


_CLIENT_TTL = timedelta(minutes=30)
_client_cache: dict[str, TelegramClient] = {}
_client_last_used: dict[str, datetime] = {}


def _cleanup_clients():
    now = datetime.utcnow()
    expired = [k for k, v in _client_last_used.items() if now - v > _CLIENT_TTL]
    for key in expired:
        client = _client_cache.pop(key, None)
        _client_last_used.pop(key, None)
        if client and client.is_connected():
            try:
                client.disconnect()
            except Exception:
                pass


async def get_client(session_string: str) -> TelegramClient:
    _cleanup_clients()
    api_id, api_hash = get_telegram_api_credentials()
    if not api_id or not api_hash:
        raise ValueError("Telegram API credentials are not configured")

    client = _client_cache.get(session_string)
    if client is None:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        _client_cache[session_string] = client

    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        raise ValueError("Telegram session is not authorized")

    _client_last_used[session_string] = datetime.utcnow()
    return client


async def resolve_peer(client: TelegramClient, peer: str):
    if isinstance(peer, str) and peer.isdigit():
        return int(peer)
    return await client.get_entity(peer)


async def list_dialogs(client: TelegramClient, limit: int = 50) -> list[dict]:
    dialogs = []
    async for dialog in client.iter_dialogs(limit=limit):
        entity = dialog.entity
        dialogs.append(
            {
                "id": getattr(entity, "id", None),
                "name": dialog.name,
                "unread_count": dialog.unread_count,
                "is_user": dialog.is_user,
                "is_group": dialog.is_group,
                "is_channel": dialog.is_channel,
            }
        )
    return dialogs


async def send_message(client: TelegramClient, peer: str, text: str) -> dict:
    entity = await resolve_peer(client, peer)
    message = await client.send_message(entity, text)
    return {
        "message_id": message.id,
        "date": message.date.isoformat() if message.date else None,
    }


async def search_messages(
    client: TelegramClient, peer: Optional[str], query: str, limit: int = 20
) -> list[dict]:
    entity = await resolve_peer(client, peer) if peer else None
    results = []
    async for message in client.iter_messages(entity, search=query, limit=limit):
        results.append(
            {
                "message_id": message.id,
                "text": message.message,
                "date": message.date.isoformat() if message.date else None,
                "sender_id": getattr(message.sender, "id", None),
            }
        )
    return results


async def message_history(
    client: TelegramClient, peer: str, limit: int = 20, before_id: Optional[int] = None
) -> list[dict]:
    entity = await resolve_peer(client, peer)
    results = []
    async for message in client.iter_messages(entity, limit=limit, max_id=before_id):
        results.append(
            {
                "message_id": message.id,
                "text": message.message,
                "date": message.date.isoformat() if message.date else None,
                "sender_id": getattr(message.sender, "id", None),
            }
        )
    return results
