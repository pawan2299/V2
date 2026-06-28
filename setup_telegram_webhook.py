import sys
import requests

def setup(token: str, service_url: str):
    url = service_url.rstrip("/") + "/telegram-webhook"
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": url},
        timeout=10
    )
    print(resp.json())

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python setup_telegram_webhook.py <TOKEN> <URL>")
    else:
        setup(sys.argv[1], sys.argv[2])
