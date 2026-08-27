import logging
import os
import sqlite3
import time

from flask import Flask, jsonify, request
from opentelemetry import trace
from UnleashClient import UnleashClient

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fivepercent.promo_service")

tracer = trace.get_tracer("fivepercent.promo_service")

RULE_LOOKUP_FLAG = "promo-rule-lookup-misconfigured"

# Simulated round-trip time to the rule store. In production the rules would
# live in a remote database, so every query pays a network round trip; the
# in-process SQLite store is free, and this sleep stands in for that cost.
RULE_STORE_RTT_SECONDS = float(os.getenv("RULE_STORE_RTT_SECONDS", "0.015"))

# Total discount is capped so stacked rules cannot exceed a sane percentage.
MAX_DISCOUNT_PERCENT = 50.0

UNLEASH_URL = os.getenv("UNLEASH_URL")
UNLEASH_API_TOKEN = os.getenv("UNLEASH_API_TOKEN")
UNLEASH_APP_NAME = os.getenv("UNLEASH_APP_NAME", "promo-service")

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


def rule_lookup_misconfigured() -> bool:
    if unleash_client is None:
        return False
    return unleash_client.is_enabled(RULE_LOOKUP_FLAG)


# code_rules maps a promo code to the rule ids it activates; rules holds the
# discount each rule contributes. Most codes map to one or two rules. VIP20
# stacks the full member-benefit list, one rule per benefit.
SEED_CODES: dict[str, list[tuple[float, str]]] = {
    "WELCOME10": [(10.0, "new customer welcome discount")],
    "FREESHIP": [(4.0, "free standard shipping")],
    "SUMMER15": [(10.0, "summer seasonal discount"), (5.0, "summer newsletter bonus")],
    "VIP20": [(0.5, f"member benefit tier {i}") for i in range(1, 36)],
}

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY, discount_percent REAL, description TEXT)")
db.execute("CREATE TABLE code_rules (code TEXT, rule_id INTEGER)")
_rule_id = 0
for _code, _rules in SEED_CODES.items():
    for _percent, _description in _rules:
        _rule_id += 1
        db.execute("INSERT INTO rules VALUES (?, ?, ?)", (_rule_id, _percent, _description))
        db.execute("INSERT INTO code_rules VALUES (?, ?)", (_code, _rule_id))
db.commit()

app = Flask(__name__)


def fetch_rule(rule_id: int) -> float:
    with tracer.start_as_current_span("fetch_rule") as span:
        span.set_attribute("promo.rule_id", rule_id)
        time.sleep(RULE_STORE_RTT_SECONDS)
        # Connection.execute() bypasses the instrumented cursor; go through
        # cursor() so the query produces a db span.
        row = db.cursor().execute("SELECT discount_percent FROM rules WHERE id = ?", (rule_id,)).fetchone()
    return row[0] if row else 0.0


def fetch_rules_batch(rule_ids: list[int]) -> list[float]:
    with tracer.start_as_current_span("fetch_rules_batch") as span:
        span.set_attribute("promo.rule_count", len(rule_ids))
        time.sleep(RULE_STORE_RTT_SECONDS)
        placeholders = ",".join("?" * len(rule_ids))
        rows = db.cursor().execute(f"SELECT discount_percent FROM rules WHERE id IN ({placeholders})", rule_ids).fetchall()
    return [row[0] for row in rows]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate")
def evaluate():
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip().upper()

    with tracer.start_as_current_span("resolve_code") as span:
        span.set_attribute("promo.code", code)
        rule_ids = [row[0] for row in db.cursor().execute("SELECT rule_id FROM code_rules WHERE code = ?", (code,)).fetchall()]
        span.set_attribute("promo.rule_count", len(rule_ids))

    if not rule_ids:
        return jsonify({"code": code, "valid": False, "discount_percent": 0.0, "rule_count": 0})

    if rule_lookup_misconfigured():
        discounts = [fetch_rule(rule_id) for rule_id in rule_ids]
    else:
        discounts = fetch_rules_batch(rule_ids)

    discount_percent = min(sum(discounts), MAX_DISCOUNT_PERCENT)
    return jsonify({"code": code, "valid": True, "discount_percent": discount_percent, "rule_count": len(rule_ids)})


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
