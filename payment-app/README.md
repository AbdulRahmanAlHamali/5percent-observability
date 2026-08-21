# Sample Payment App

## Purpose
This app is a separate, small checkout flow used for the log analytics lab. It has no Prometheus metrics of its own; it exists to produce realistic structured payment logs for log-based investigation exercises.

## Endpoints
- `/checkout` (`GET`) renders a checkout page for a constant product at a freshly randomized price.
- `/checkout` (`POST`) accepts the submitted payment and address form, runs a fake payment decision, and renders a success or decline page.
- `/healthz` returns a readiness and liveness response for Kubernetes probes.

## Structured Logs
The app writes one JSON object per line to stdout for each of these events, separate from the default Flask/Werkzeug request log line. Each line is valid JSON on its own (no timestamp/level prefix), so it can be parsed directly with LogQL's `| json`.

- `checkout_page_viewed` — emitted on `GET /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `ip`.
- `payment_accepted` / `payment_rejected` — emitted on `POST /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `country`, `ip`, `card_last4`, `status`, `rejection_reason` (`null` when accepted).

`checkout_id` is generated on the `GET` request and round-tripped through a hidden form field, so a page view and its resulting payment attempt can be correlated even though they are separate HTTP requests.

The decision logic is a fake baseline decline rate (`~8%`) with a randomly chosen reason (`insufficient_funds`, `card_declined`, `invalid_cvv`, `suspected_fraud`, `address_mismatch`). It does not yet encode any country- or amount-specific behavior.

No card number, expiry, or CVV is ever logged in full; only the last 4 digits of the card number (`card_last4`).
