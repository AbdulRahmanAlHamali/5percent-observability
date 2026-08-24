import json
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any

from flask import Flask, Response, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

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
    ("JP", "Japan"),
    ("SY", "Syria"),
]

DECLINE_REASONS = ["insufficient_funds", "card_declined", "invalid_cvv", "suspected_fraud", "address_mismatch"]
DECLINE_WEIGHTS = [0.35, 0.30, 0.15, 0.10, 0.10]
BASELINE_DECLINE_RATE = 0.08

CHECKOUT_VIEWS = Counter(
    "fivepercent_payment_checkout_views_total",
    "Total checkout page views.",
)
CHECKOUT_SUBMISSIONS = Counter(
    "fivepercent_payment_checkout_submissions_total",
    "Total checkout form submissions by status.",
    ["status"],
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


def generate_price() -> float:
    return round(random.uniform(*PRICE_RANGE), 2)


def client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")


def evaluate_payment(amount: float, country: str, card_number: str) -> tuple[bool, str | None]:
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

    accepted, reason = evaluate_payment(amount, country, card_number)
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
    )

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
