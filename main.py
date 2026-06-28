from __future__ import annotations
import logging
import sys
import threading
import time
from flask import Flask, request, jsonify
from config import SETTINGS
from database import init_db, is_safe_mode, set_state, get_state
from security import verify_signature
from bot_logic import handle_comment, handle_new_follower, handle_dm
from telegram_bot import handle_update, _send, get_webhook_info, register_telegram_webhook
from instagram_api import check_token_validity

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_init_done = False
_init_lock = threading.Lock()

# Global Rate Limiting
_reply_counts = []
_reply_lock = threading.Lock()
MAX_REPLIES_PER_MINUTE = 20


def _check_rate_limit() -> bool:
    """Global safety limit to prevent loops from exploding."""
    now = time.time()
    with _reply_lock:
        # Cleanup old entries
        while _reply_counts and now - _reply_counts[0] > 60:
            _reply_counts.pop(0)
        
        if len(_reply_counts) >= MAX_REPLIES_PER_MINUTE:
            if not is_safe_mode():
                logger.critical(f"Global rate limit hit ({len(_reply_counts)}/min). Enabling Safe Mode.")
                set_state("safe_mode", "true")
                _send(
                    SETTINGS.telegram_chat_id,
                    "🚨 <b>Global Rate Limit Triggered!</b>\n\n"
                    f"Bot sent {len(_reply_counts)} replies in 60s. Safe Mode enabled automatically to prevent loops."
                )
            return False
        
        _reply_counts.append(now)
        return True


def _startup():
    global _init_done
    with _init_lock:
        if _init_done:
            return

    try:
        logger.info("Starting Krishna Bot initialization...")
        init_db()
        
        # Diagnostics
        logger.info(f"Telegram Bot Token loaded: {'✅' if SETTINGS.telegram_bot_token else '❌'}")
        logger.info(f"Telegram Chat ID loaded: {'✅' if SETTINGS.telegram_chat_id else '❌'}")
        
        # Register Webhook
        register_telegram_webhook()
        
        ig_valid = check_token_validity("ig_user")
        page_valid = check_token_validity("page_access")
        
        status_msg = "🦚 <b>Krishna Bot Startup</b>\n\n"
        status_msg += f"IG User Token: {'✅ Valid' if ig_valid else '❌ Invalid'}\n"
        status_msg += f"Page Token: {'✅ Valid' if page_valid else '❌ Invalid'}\n"
        
        wh_info = get_webhook_info()
        wh_url = "None"
        if wh_info.get("ok"):
            wh_url = wh_info.get("result", {}).get("url", "None")
            status_msg += f"Telegram Webhook: <code>{wh_url}</code>"
        
        logger.info(f"Webhook URL: {wh_url}")
        
        _send(SETTINGS.telegram_chat_id, status_msg)
        
        if not ig_valid and not page_valid:
            logger.critical("Both tokens are invalid. Bot will not function.")
        
        with _init_lock:
            _init_done = True
        logger.info("🦚 Krishna Bot ready!")
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        sys.exit(1)


_startup()


@app.before_request
def wake_up():
    from database import init_pool
    try:
        init_pool()
    except Exception:
        pass


@app.get("/")
def health():
    return jsonify({
        "status": "🦚 Krishna Bot is Live!",
        "env": SETTINGS.environment,
        "safe_mode": is_safe_mode()
    }), 200


@app.get("/webhook")
def verify_webhook():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == SETTINGS.verify_token):
        logger.info("Webhook verified by Meta.")
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@app.post("/webhook")
def webhook():
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.data, sig):
        logger.warning("Invalid webhook signature!")
        return "Forbidden", 403

    data = request.get_json(silent=True) or {}

    def process():
        # Global Rate Limit Check
        if not _check_rate_limit() and not is_safe_mode():
            return

        for entry in data.get("entry", []):
            # Instagram DMs come through entry.messaging
            for msg_event in entry.get("messaging", []):
                handle_dm(msg_event)

            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field == "comments":
                    handle_comment(value)
                elif field == "follows":
                    handle_new_follower(
                        value.get("id", ""),
                        value.get("username", "")
                    )
                elif field == "messages":
                    handle_dm(value)

    threading.Thread(target=process, daemon=True).start()
    return "OK", 200


@app.post("/telegram-webhook")
def telegram_webhook():
    try:
        update = request.get_json(silent=True) or {}
        threading.Thread(
            target=handle_update, args=(update,), daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error in telegram_webhook endpoint: {e}")
    return "OK", 200


@app.get("/weekly-report")
def weekly_report_trigger():
    try:
        from database import get_stats
        from gemini_client import generate_weekly_insight
        stats = get_stats()
        insight = generate_weekly_insight(stats)
        if insight:
            _send(
                SETTINGS.telegram_chat_id,
                f"📊 <b>Weekly Krishna Bot Report</b>\n\n"
                f"Total Replies: {stats['total_comments_replied']}\n"
                f"Welcome DMs: {stats['welcome_dms_sent']}\n\n"
                f"🤖 <b>Gemini Insights:</b>\n{insight}"
            )
        return jsonify({"status": "report sent"}), 200
    except Exception as e:
        logger.error(f"Weekly report error: {e}")
        return jsonify({"error": str(e)}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled error: {e}", exc_info=True)
    try:
        _send(
            SETTINGS.telegram_chat_id,
            f"🔴 <b>Bot Error!</b>\n\n<code>{str(e)[:300]}</code>"
        )
    except Exception:
        pass
    return jsonify({"error": "Internal server error"}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=SETTINGS.port, debug=False)
