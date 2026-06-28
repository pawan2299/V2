from __future__ import annotations
import logging
import time
from collections import deque
from google import genai
from config import SETTINGS
from database import increment_gemini_count, get_state, set_state

logger = logging.getLogger(__name__)

_client: genai.Client | None = None
_calls: deque[float] = deque()
MAX_PER_MINUTE = 15


def _get_client() -> genai.Client | None:
    global _client
    if _client is None:
        try:
            _client = genai.Client(api_key=SETTINGS.gemini_api_key)
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")
    return _client


def _track_call(count: int):
    """1400+ होने पर Telegram alert।"""
    if count >= 1400:
        logger.warning(f"Gemini daily limit approaching: {count}/1500")
        try:
            from telegram_bot import _send
            _send(
                SETTINGS.telegram_chat_id,
                f"⚠️ <b>Gemini Limit Warning</b>\n\n"
                f"आज {count}/1500 calls हो गई हैं!\n"
                f"Switching to hardcoded replies soon."
            )
        except Exception:
            pass


def can_use_gemini() -> bool:
    # 1. Minute Rate Limit
    now = time.time()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= MAX_PER_MINUTE:
        return False

    # 2. Circuit Breaker
    cb_until = get_state("circuit_breaker_until")
    if cb_until and cb_until != "0":
        try:
            if now < float(cb_until):
                return False
            else:
                # Reset circuit breaker after cooldown
                set_state("circuit_breaker_until", "0")
                set_state("consecutive_429s", "0")
        except ValueError:
            pass

    return True


def _handle_gemini_error(e: Exception):
    error_msg = str(e)
    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
        count = int(get_state("consecutive_429s") or 0) + 1
        set_state("consecutive_429s", str(count))
        logger.warning(f"Gemini 429 received. Consecutive count: {count}")
        
        if count >= 3:
            # Trip the circuit for 30 minutes
            cooldown = time.time() + (30 * 60)
            set_state("circuit_breaker_until", str(cooldown))
            logger.critical("Gemini Circuit Breaker TRIPPED for 30 mins.")
            try:
                from telegram_bot import _send
                _send(
                    SETTINGS.telegram_chat_id,
                    "🚨 <b>Gemini Circuit Breaker!</b>\n\n"
                    "Too many 429 errors. AI replies disabled for 30 mins.\n"
                    "Bot will use fallback/keywords only."
                )
            except Exception:
                pass
    else:
        # Reset 429 count on non-429 errors
        set_state("consecutive_429s", "0")


def generate_reply(comment_text: str) -> str | None:
    if not can_use_gemini():
        return None

    client = _get_client()
    if not client:
        return None

    prompt = (
        "You are the voice of the Instagram page @krishna.verse.ai — a devotional page "
        "dedicated to Lord Krishna and Radha Rani. Reply to this comment with warmth and "
        "spiritual love. Keep it SHORT (max 12 words), natural, and end with "
        "'Radhe Radhe 🙏' or 'Jai Shri Krishna ✨'. "
        "Never mention you're an AI. Match the language of the comment."
        f"\nComment: {comment_text}"
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        text = (resp.text or "").strip().replace('"', "").replace("'", "")
        return text[:200] if text else None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        _handle_gemini_error(e)
        return None


def generate_dm_reply(message_text: str) -> str | None:
    if not can_use_gemini():
        return None

    client = _get_client()
    if not client:
        return None

    prompt = (
        "You are the voice of @krishna.verse.ai — a devotional Krishna page. "
        "Someone sent you a direct message. Reply with warmth, spirituality, and love. "
        "Keep it under 50 words. Natural tone, not robotic. "
        "End with Radhe Radhe 🙏 or Jai Shri Krishna ✨. "
        "Match the language of the message (Hindi or English)."
        f"\nMessage: {message_text}"
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        return (resp.text or "").strip()[:300]
    except Exception as e:
        logger.error(f"Gemini DM reply error: {e}")
        _handle_gemini_error(e)
        return None


def generate_welcome_dm(username: str) -> str | None:
    if not can_use_gemini():
        return None

    client = _get_client()
    if not client:
        return None

    prompt = (
        f"Write a warm, short welcome DM (max 40 words) for a new Instagram follower "
        f"named '{username}' who just followed @krishna.verse.ai — a devotional Krishna page. "
        "Make it feel personal and spiritual. Use 2-3 relevant emojis. "
        "End with Radhe Radhe 🙏. Don't mention AI."
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        return (resp.text or "").strip()[:400]
    except Exception as e:
        logger.error(f"Gemini welcome DM error: {e}")
        _handle_gemini_error(e)
        return None


def is_spam_or_negative(text: str) -> bool:
    if not can_use_gemini():
        return False

    client = _get_client()
    if not client:
        return False

    prompt = (
        "Classify this Instagram comment as SPAM or NEGATIVE or SAFE.\n"
        "SPAM = promotional, irrelevant, bot-like, repeated characters\n"
        "NEGATIVE = hate, abuse, offensive, discouraging\n"
        "SAFE = genuine, devotional, curious, appreciative\n"
        "Reply with exactly one word: SPAM, NEGATIVE, or SAFE\n"
        f"Comment: {text}"
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        result = (resp.text or "").strip().upper()
        return result in ("SPAM", "NEGATIVE")
    except Exception as e:
        logger.error(f"Gemini spam check error: {e}")
        _handle_gemini_error(e)
        return False


def generate_caption(topic: str) -> str | None:
    client = _get_client()
    if not client:
        return None

    prompt = (
        "Write an Instagram caption for a devotional Krishna page (@krishna.verse.ai). "
        f"Topic: {topic}\n\n"
        "Rules:\n"
        "- 3-4 lines max\n"
        "- Spiritual and emotional tone\n"
        "- 5-8 relevant hashtags at the end\n"
        "- Mix of Hindi and English is fine\n"
        "- End with Radhe Radhe 🙏 or Jai Shri Krishna ✨"
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        return (resp.text or "").strip()
    except Exception as e:
        logger.error(f"Caption generation error: {e}")
        _handle_gemini_error(e)
        return None


def generate_weekly_insight(stats: dict) -> str | None:
    client = _get_client()
    if not client:
        return None

    prompt = (
        "You are a social media analyst for @krishna.verse.ai — a devotional Instagram page.\n"
        f"This week's stats:\n"
        f"- Total comments replied: {stats.get('total_comments_replied', 0)}\n"
        f"- Last 24h replies: {stats.get('last_24h_replies', 0)}\n"
        f"- Welcome DMs sent: {stats.get('welcome_dms_sent', 0)}\n\n"
        "Give 3 short, practical suggestions to grow this page. "
        "Under 100 words total. Be specific."
    )

    try:
        _calls.append(time.time())
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        set_state("consecutive_429s", "0") # Reset on success
        count = increment_gemini_count()
        _track_call(count)
        return (resp.text or "").strip()
    except Exception as e:
        logger.error(f"Weekly insight error: {e}")
        _handle_gemini_error(e)
        return None
