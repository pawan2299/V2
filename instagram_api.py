from __future__ import annotations
import logging
import requests
from config import SETTINGS

logger = logging.getLogger(__name__)

BASE = "https://graph.facebook.com/v25.0"
TIMEOUT = 10


def _post(endpoint: str, data: dict, token: str) -> bool:
    """Instagram Graph API POST — clean wrapper."""
    data["access_token"] = token
    try:
        resp = requests.post(f"{BASE}/{endpoint}", json=data, timeout=TIMEOUT)
        if resp.ok:
            return True
        logger.error(f"Instagram API error {resp.status_code}: {resp.text[:200]}")
        return False
    except requests.RequestException as e:
        logger.error(f"Instagram request failed: {e}")
        return False


def reply_to_comment(comment_id: str, message: str) -> bool:
    # Comments require User Access Token
    return _post(f"{comment_id}/replies", {"message": message}, SETTINGS.ig_user_token)


def send_dm(user_id: str, message: str) -> bool:
    # DMs/Messaging requires Page Access Token
    return _post(
        f"{SETTINGS.page_id}/messages",
        {
            "recipient": {"id": user_id},
            "message": {"text": message},
            "messaging_type": "RESPONSE",
        },
        SETTINGS.page_access_token
    )


def check_token_validity(token_type: str = "ig_user") -> bool:
    """
    Meta debug endpoint से token verify करो।
    """
    token = SETTINGS.ig_user_token if token_type == "ig_user" else SETTINGS.page_access_token
    try:
        resp = requests.get(
            "https://graph.facebook.com/debug_token",
            params={
                "input_token": token,
                "access_token": token
            },
            timeout=10
        )
        if not resp.ok:
            logger.error(f"{token_type} Token debug failed: {resp.text[:200]}")
            return False

        data = resp.json().get("data", {})
        is_valid = data.get("is_valid", False)
        
        if is_valid:
            logger.info(f"✅ {token_type} Token is valid.")
            return True
        else:
            error = data.get("error", {})
            logger.error(f"❌ {token_type} Token invalid: {error.get('message', 'Unknown error')}")
            return False

    except Exception as e:
        logger.error(f"{token_type} Token check error: {e}")
        return False
