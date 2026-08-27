import json
import logging
import os
import random
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from flask import Flask, Response, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from UnleashClient import UnleashClient

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fivepercent.payment_app")

event_logger = logging.getLogger("fivepercent.payment_app.events")
event_logger.propagate = False
event_logger.setLevel(logging.INFO)
_event_handler = logging.StreamHandler(sys.stdout)
_event_handler.setFormatter(logging.Formatter("%(message)s"))
event_logger.addHandler(_event_handler)

PRODUCT_NAME = "Wireless Noise-Cancelling Headphones"
CURRENCY = "USD"
PRICE_RANGE = (20.0, 900.0)

COUNTRIES = [
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("CA", "Canada"),
    ("AU", "Australia"),
    ("BR", "Brazil"),
    ("IN", "India"),
    ("SY", "Syria"),
]

DECLINE_REASONS = ["insufficient_funds", "card_declined", "invalid_cvv", "suspected_fraud", "address_mismatch"]
DECLINE_WEIGHTS = [0.35, 0.30, 0.15, 0.10, 0.10]
BASELINE_DECLINE_RATE = 0.08

FRAUD_CHECK_FLAG = "payment-fraud-check-misconfigured"
FRAUD_CHECK_COUNTRY = "SY"
FRAUD_CHECK_AMOUNT_THRESHOLD = 500.0

AUDIT_LOG_FLAG = "payment-audit-log-misconfigured"

# Intended as a bounded ring buffer (last 500 transactions) so fraud-review
# staff can look up recent activity without a database round trip. Ships as
# a plain, never-trimmed list instead: every transaction after this flag is
# enabled is retained forever.
_TRANSACTION_AUDIT_LOG: list[dict[str, Any]] = []

BULK_ORDER_FLAG = "payment-bulk-order-fulfillment-enabled"
BULK_ORDER_CHUNK_SIZE = 2_000
BULK_ORDER_CHUNK_DELAY_SECONDS = 0.1

# A single accepted order should never need more than a few dozen units, but
# nothing here checks that: `quantity` is taken from the request as-is. A
# wholesale-integration client sending an inflated value causes this list to
# grow by one entry per unit with no upper bound.
_FULFILLMENT_MANIFEST: list[dict[str, Any]] = []

UNLEASH_URL = os.getenv("UNLEASH_URL")
UNLEASH_API_TOKEN = os.getenv("UNLEASH_API_TOKEN")
UNLEASH_APP_NAME = os.getenv("UNLEASH_APP_NAME", "payment-app")

unleash_client: UnleashClient | None = None
if UNLEASH_URL and UNLEASH_API_TOKEN:
    unleash_client = UnleashClient(
        url=UNLEASH_URL,
        app_name=UNLEASH_APP_NAME,
        custom_headers={"Authorization": UNLEASH_API_TOKEN},
    )
    try:
        unleash_client.initialize_client()
    except Exception:
        logger.exception("Failed to connect to Unleash; feature flags will default to disabled")
        unleash_client = None
else:
    logger.info("UNLEASH_URL/UNLEASH_API_TOKEN not set; feature flags will default to disabled")


def fraud_check_misconfigured() -> bool:
    if unleash_client is None:
        return False
    return unleash_client.is_enabled(FRAUD_CHECK_FLAG)


def audit_log_misconfigured() -> bool:
    if unleash_client is None:
        return False
    return unleash_client.is_enabled(AUDIT_LOG_FLAG)


def bulk_order_fulfillment_enabled() -> bool:
    if unleash_client is None:
        return False
    return unleash_client.is_enabled(BULK_ORDER_FLAG)


CHECKOUT_VIEWS = Counter(
    "fivepercent_payment_checkout_views_total",
    "Total checkout page views.",
)
CHECKOUT_SUBMISSIONS = Counter(
    "fivepercent_payment_checkout_submissions_total",
    "Total checkout form submissions by status.",
    ["status"],
)
AUDIT_LOG_ENTRIES = Gauge(
    "fivepercent_payment_audit_log_entries",
    "Number of entries currently held in the in-memory transaction audit log.",
)

app = Flask(__name__)


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
    }
    payload.update(fields)
    getattr(event_logger, level)(json.dumps(payload))


def _process_bulk_order(checkout_id: str, product: str, quantity: int) -> None:
    processed = 0
    while processed < quantity:
        chunk = min(BULK_ORDER_CHUNK_SIZE, quantity - processed)
        for offset in range(chunk):
            _FULFILLMENT_MANIFEST.append(
                {
                    "checkout_id": checkout_id,
                    "unit_id": f"{checkout_id}-{processed + offset}",
                    "product": product,
                    "serial": uuid.uuid4().hex,
                    "packed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        processed += chunk
        log_event(
            "bulk_order_manifest_chunk_processed",
            checkout_id=checkout_id,
            quantity=quantity,
            units_processed=processed,
        )
        time.sleep(BULK_ORDER_CHUNK_DELAY_SECONDS)


def generate_price() -> float:
    return round(random.uniform(*PRICE_RANGE), 2)


def client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")


def evaluate_payment(amount: float, country: str, card_number: str, fraud_check_bug_enabled: bool) -> tuple[bool, str | None]:
    if fraud_check_bug_enabled and country == FRAUD_CHECK_COUNTRY and amount > FRAUD_CHECK_AMOUNT_THRESHOLD:
        return False, "suspected_fraud"

    if random.random() < BASELINE_DECLINE_RATE:
        reason = random.choices(DECLINE_REASONS, weights=DECLINE_WEIGHTS)[0]
        return False, reason
    return True, None


@app.errorhandler(Exception)
def handle_exception(error: Exception) -> tuple[Response, int]:
    logger.exception("Unhandled request error")
    return Response("internal server error", status=HTTPStatus.INTERNAL_SERVER_ERROR)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/checkout")
def checkout() -> str:
    CHECKOUT_VIEWS.inc()

    checkout_id = uuid.uuid4().hex
    amount = generate_price()

    log_event(
        "checkout_page_viewed",
        checkout_id=checkout_id,
        product=PRODUCT_NAME,
        amount=amount,
        currency=CURRENCY,
        ip=client_ip(),
    )

    return render_template(
        "checkout.html",
        checkout_id=checkout_id,
        product=PRODUCT_NAME,
        amount=f"{amount:.2f}",
        currency=CURRENCY,
        countries=COUNTRIES,
    )


@app.post("/checkout")
def submit_checkout() -> str:
    checkout_id = request.form.get("checkout_id", "")
    product = request.form.get("product", PRODUCT_NAME)
    currency = request.form.get("currency", CURRENCY)
    country = request.form.get("country", "US")
    card_number = request.form.get("card_number", "")
    card_last4 = card_number[-4:] if len(card_number) >= 4 else "0000"

    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        amount = 0.0

    # Undocumented: only a wholesale-integration client sending `quantity`
    # directly to this endpoint ever sets this above 1 - the checkout UI has
    # no field for it.
    try:
        quantity = max(1, int(request.form.get("quantity", "1")))
    except ValueError:
        quantity = 1

    fraud_check_bug_enabled = fraud_check_misconfigured()
    accepted, reason = evaluate_payment(amount, country, card_number, fraud_check_bug_enabled)
    CHECKOUT_SUBMISSIONS.labels("succeeded" if accepted else "failed").inc()

    log_event(
        "payment_accepted" if accepted else "payment_rejected",
        level="info" if accepted else "warning",
        checkout_id=checkout_id,
        product=product,
        amount=amount,
        currency=currency,
        country=country,
        ip=client_ip(),
        card_last4=card_last4,
        status="accepted" if accepted else "rejected",
        rejection_reason=reason,
        quantity=quantity,
    )

    if accepted and quantity > 1 and bulk_order_fulfillment_enabled():
        threading.Thread(
            target=_process_bulk_order,
            args=(checkout_id, product, quantity),
            daemon=True,
        ).start()

    if audit_log_misconfigured():
        page_snapshot = render_template(
            "checkout.html",
            checkout_id=checkout_id,
            product=product,
            amount=f"{amount:.2f}",
            currency=currency,
            countries=COUNTRIES,
        )
        _TRANSACTION_AUDIT_LOG.append(
            {
                "checkout_id": checkout_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "product": product,
                "amount": amount,
                "currency": currency,
                "country": country,
                "full_name": request.form.get("full_name", ""),
                "email": request.form.get("email", ""),
                "address_line1": request.form.get("address_line1", ""),
                "city": request.form.get("city", ""),
                "postal_code": request.form.get("postal_code", ""),
                "card_number": card_number,
                "card_expiry": request.form.get("card_expiry", ""),
                # Raw CVV must never be retained past authorization; keeping it
                # here is itself a second, independent bug.
                "card_cvv": request.form.get("card_cvv", ""),
                "ip": client_ip(),
                "accepted": accepted,
                "rejection_reason": reason,
                "page_snapshot": page_snapshot,
            }
        )
        AUDIT_LOG_ENTRIES.set(len(_TRANSACTION_AUDIT_LOG))

    return render_template(
        "result.html",
        accepted=accepted,
        product=product,
        amount=f"{amount:.2f}",
        currency=currency,
    )


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
