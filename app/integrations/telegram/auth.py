from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import secrets

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

from app.config.store import get_telegram_api_credentials


LOGIN_TTL = timedelta(minutes=10)


@dataclass
class LoginState:
    user_id: int
    phone: str
    session_string: str
    phone_code_hash: str
    created_at: datetime


_login_states: dict[str, LoginState] = {}


def _cleanup_expired():
    now = datetime.utcnow()
    expired = [k for k, v in _login_states.items() if now - v.created_at > LOGIN_TTL]
    for key in expired:
        _login_states.pop(key, None)


def _get_state(login_id: str) -> Optional[LoginState]:
    _cleanup_expired()
    return _login_states.get(login_id)


async def start_login(user_id: int, phone: str) -> str:
    api_id, api_hash = get_telegram_api_credentials()
    if not api_id or not api_hash:
        raise ValueError("Telegram API credentials are not configured")

    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        result = await client.send_code_request(phone)
        login_id = secrets.token_urlsafe(24)
        _login_states[login_id] = LoginState(
            user_id=user_id,
            phone=phone,
            session_string=session.save(),
            phone_code_hash=result.phone_code_hash,
            created_at=datetime.utcnow(),
        )
        return login_id
    finally:
        await client.disconnect()


async def verify_code(login_id: str, code: str, user_id: int) -> dict:
    state = _get_state(login_id)
    if not state:
        raise ValueError("Login session expired or invalid")
    if state.user_id != user_id:
        raise ValueError("Login session does not belong to this user")

    api_id, api_hash = get_telegram_api_credentials()
    if not api_id or not api_hash:
        raise ValueError("Telegram API credentials are not configured")

    session = StringSession(state.session_string)
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=state.phone,
                code=code,
                phone_code_hash=state.phone_code_hash,
            )
        except SessionPasswordNeededError:
            return {"requires_password": True}

        me = await client.get_me()
        _login_states.pop(login_id, None)
        return {
            "requires_password": False,
            "session_string": session.save(),
            "meta": {
                "telegram_user_id": getattr(me, "id", None),
                "username": getattr(me, "username", None),
                "phone": state.phone,
            },
        }
    finally:
        await client.disconnect()


async def submit_password(login_id: str, password: str, user_id: int) -> dict:
    state = _get_state(login_id)
    if not state:
        raise ValueError("Login session expired or invalid")
    if state.user_id != user_id:
        raise ValueError("Login session does not belong to this user")

    api_id, api_hash = get_telegram_api_credentials()
    if not api_id or not api_hash:
        raise ValueError("Telegram API credentials are not configured")

    session = StringSession(state.session_string)
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        _login_states.pop(login_id, None)
        return {
            "session_string": session.save(),
            "meta": {
                "telegram_user_id": getattr(me, "id", None),
                "username": getattr(me, "username", None),
                "phone": state.phone,
            },
        }
    finally:
        await client.disconnect()
