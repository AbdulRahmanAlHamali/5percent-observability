import os
import random
import re
import time

import requests

TARGET_URL = os.getenv("TARGET_URL", "http://payment-app").rstrip("/")
MIN_DELAY_SECONDS = float(os.getenv("MIN_DELAY_SECONDS", "0.2"))
MAX_DELAY_SECONDS = float(os.getenv("MAX_DELAY_SECONDS", "1.5"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
CHECKOUT_CHURN_RATE = float(os.getenv("CHECKOUT_CHURN_RATE", "0.05"))
BULK_ORDER_RATE = float(os.getenv("BULK_ORDER_RATE", "0.005"))
BULK_ORDER_MIN_QUANTITY = int(os.getenv("BULK_ORDER_MIN_QUANTITY", "500000"))
BULK_ORDER_MAX_QUANTITY = int(os.getenv("BULK_ORDER_MAX_QUANTITY", "2000000"))

COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "BR", "IN", "SY"]
CARD_NUMBERS = ["4111111111111111", "4242424242424242", "5555555555554444", "378282246310005"]

CHECKOUT_ID_PATTERN = re.compile(r'name="checkout_id" value="([^"]*)"')
AMOUNT_PATTERN = re.compile(r'name="amount" value="([^"]*)"')


def log(message: str) -> None:
    print(f"[traffic-generator] {message}", flush=True)


def run_one_checkout(session: requests.Session) -> None:
    get_response = session.get(f"{TARGET_URL}/checkout", timeout=REQUEST_TIMEOUT_SECONDS)
    get_response.raise_for_status()

    checkout_id_match = CHECKOUT_ID_PATTERN.search(get_response.text)
    amount_match = AMOUNT_PATTERN.search(get_response.text)
    if not checkout_id_match or not amount_match:
        log("could not find checkout_id/amount in checkout page response")
        return

    checkout_id = checkout_id_match.group(1)
    amount = amount_match.group(1)

    if random.random() < CHECKOUT_CHURN_RATE:
        log(f"abandoned  {checkout_id[:8]}  ${amount}")
        return

    data = {
        "checkout_id": checkout_id,
        "amount": amount,
        "currency": "USD",
        "country": random.choice(COUNTRIES),
        "card_number": random.choice(CARD_NUMBERS),
    }

    # Simulates a rare, misbehaving wholesale-integration client hitting this
    # same checkout endpoint directly with a bulk order instead of going
    # through the normal single-item UI flow.
    bulk_order = random.random() < BULK_ORDER_RATE
    if bulk_order:
        data["quantity"] = random.randint(BULK_ORDER_MIN_QUANTITY, BULK_ORDER_MAX_QUANTITY)

    post_response = session.post(
        f"{TARGET_URL}/checkout",
        data=data,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    post_response.raise_for_status()

    if bulk_order:
        log(f"HTTP {post_response.status_code}  {checkout_id[:8]}  ${amount}  bulk qty={data['quantity']}")
    else:
        log(f"HTTP {post_response.status_code}  {checkout_id[:8]}  ${amount}")


def main() -> None:
    log(f"starting against {TARGET_URL}, delay {MIN_DELAY_SECONDS}-{MAX_DELAY_SECONDS}s")
    session = requests.Session()

    while True:
        try:
            run_one_checkout(session)
        except requests.RequestException as error:
            log(f"request failed: {error}")

        time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))


if __name__ == "__main__":
    main()
