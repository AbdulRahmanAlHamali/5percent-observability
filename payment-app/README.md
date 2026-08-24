# Sample Payment App

## Purpose
This app is a separate, small checkout flow used for the log analytics lab. It exists to produce realistic structured payment logs and basic Prometheus metrics for investigation exercises.

## Endpoints
- `/checkout` (`GET`) renders a checkout page for a constant product at a freshly randomized price.
- `/checkout` (`POST`) accepts the submitted payment and address form, runs a fake payment decision, and renders a success or decline page.
- `/healthz` returns a readiness and liveness response for Kubernetes probes.
- `/metrics` exposes Prometheus metrics.

## Metrics
- `fivepercent_payment_checkout_views_total` counts every `GET /checkout` page view.
- `fivepercent_payment_checkout_submissions_total` counts every `POST /checkout` submission, labeled `status` (`succeeded` or `failed`).

## Structured Logs
The app writes one JSON object per line to stdout for each of these events, separate from the default Flask/Werkzeug request log line. Each line is valid JSON on its own (no timestamp/level prefix), so it can be parsed directly with LogQL's `| json`.

- `checkout_page_viewed` — emitted on `GET /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `ip`.
- `payment_accepted` / `payment_rejected` — emitted on `POST /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `country`, `ip`, `card_last4`, `status`, `rejection_reason` (`null` when accepted).

`checkout_id` is generated on the `GET` request and round-tripped through a hidden form field, so a page view and its resulting payment attempt can be correlated even though they are separate HTTP requests.

The decision logic is a fake baseline decline rate (`~8%`) with a randomly chosen reason (`insufficient_funds`, `card_declined`, `invalid_cvv`, `suspected_fraud`, `address_mismatch`), plus an optional, feature-flag-gated misconfiguration described below.

No card number, expiry, or CVV is ever logged in full; only the last 4 digits of the card number (`card_last4`).

## Feature Flag: Simulated Fraud-Check Misconfiguration

The app checks a boolean Unleash feature flag named `payment-fraud-check-misconfigured`. When enabled, every payment where `country == "SY"` and `amount > 500` is unconditionally rejected with `rejection_reason: "suspected_fraud"`, before the normal random decline logic runs. Payments outside that country/amount combination are unaffected either way.

This exists so an instructor can flip the flag live in the Unleash UI to simulate a fraud-detection rollout that misbehaves for a specific country and amount range — the scenario this lab is built around. The `payment_accepted`/`payment_rejected` log events include a `fraud_check_flag_enabled` field reflecting the flag's state at evaluation time, independent of whether that particular transaction matched the country/amount condition, so a log-based investigation can correlate a rejection-rate change against when the flag was flipped.

The app connects to Unleash using these environment variables:

- `UNLEASH_URL` — the Unleash Client API base URL (e.g. `http://unleash.feature-flags.svc.cluster.local:4242/api`).
- `UNLEASH_API_TOKEN` — a backend/client API token, passed as the `Authorization` header value.
- `UNLEASH_APP_NAME` — the app name reported to Unleash (defaults to `payment-app`).

If `UNLEASH_URL` or `UNLEASH_API_TOKEN` is unset, or the Unleash server is unreachable at startup, the app logs a warning and the flag simply defaults to disabled — the app does not fail to start. This makes Unleash a fully optional dependency for local development.
