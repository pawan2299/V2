# 🦚 Instagram Krishna Bot — नया Robust System

तुमने बिल्कुल सही किया जो scratch से शुरू करने का सोचा। पुराना codebase ज़्यादा AI से edit होते-होते fragile हो गया था।

---

## 🎯 तुम्हारी Requirements — Clear Summary

1. **Comment Reply System** — छोटे comments → hardcoded, बड़े comments → Gemini
2. **Gemini Fallback** — limit खत्म हो तो smart hardcoded replies
3. **No Duplicate Replies** — एक comment पर एक ही बार reply
4. **New Follower DM** — automatic welcome message
5. **Telegram Control Panel** — bot start/stop, Gemini on/off
6. **Render + Neon.tech + UptimeRobot** deployment

---

## 🏗️ Architecture — Fresh & Clean

```
main.py              ← Flask app, webhook routes
config.py            ← Settings from env
database.py          ← Neon PostgreSQL (simple & clean)
bot_logic.py         ← Comment classification + replies
gemini_client.py     ← Gemini wrapper with rate limiting
telegram_bot.py      ← Admin commands via webhook
security.py          ← HMAC verification
```

**State management** सिर्फ 2 tables:
- `processed_comments` — duplicate check के लिए
- `dm_cooldowns` — follower DM rate limit

**Bot state** (paused/gemini_off) → Neon DB में, in-memory नहीं — ताकि Render restart पर भी याद रहे।

---

## 📊 Comment Classification Logic (2026 Standard)

```
Comment length < 5 chars   → emoji/short → hardcoded reply
Comment = greeting words   → hardcoded reply  
Comment length 5-30 chars  → short praise → hardcoded reply
Comment length > 30 chars  → Gemini (if available)
Gemini unavailable         → smart fallback by detected tone
```

यही approach professional accounts use करते हैं — **Gemini calls बचाओ जहाँ ज़रूरी नहीं।**
