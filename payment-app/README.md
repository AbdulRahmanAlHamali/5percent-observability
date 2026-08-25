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
- `fivepercent_payment_audit_log_entries` is a gauge tracking the size of the in-memory transaction audit log described below.

## Structured Logs
The app writes one JSON object per line to stdout for each of these events, separate from the default Flask/Werkzeug request log line. Each line is valid JSON on its own (no timestamp/level prefix), so it can be parsed directly with LogQL's `| json`.

- `checkout_page_viewed` — emitted on `GET /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `ip`.
- `payment_accepted` / `payment_rejected` — emitted on `POST /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `country`, `ip`, `card_last4`, `status`, `rejection_reason` (`null` when accepted).

`checkout_id` is generated on the `GET` request and round-tripped through a hidden form field, so a page view and its resulting payment attempt can be correlated even though they are separate HTTP requests.

The decision logic is a fake baseline decline rate (`~8%`) with a randomly chosen reason (`insufficient_funds`, `card_declined`, `invalid_cvv`, `suspected_fraud`, `address_mismatch`), plus an optional, feature-flag-gated misconfiguration described below.

No card number, expiry, or CVV is ever logged in full; only the last 4 digits of the card number (`card_last4`).

## Feature Flag: Simulated Fraud-Check Misconfiguration

The app checks a boolean Unleash feature flag named `payment-fraud-check-misconfigured`. When enabled, every payment where `country == "SY"` and `amount > 500` is unconditionally rejected with `rejection_reason: "suspected_fraud"`, before the normal random decline logic runs. Payments outside that country/amount combination are unaffected either way.

This exists so an instructor can flip the flag live in the Unleash UI to simulate a fraud-detection rollout that misbehaves for a specific country and amount range — the scenario this lab is built around.

## Feature Flag: Simulated Memory Leak (Unbounded Audit Log)

The app also checks a second boolean Unleash feature flag, `payment-audit-log-misconfigured`. When enabled, every `POST /checkout` submission appends a record to an in-memory list (`_TRANSACTION_AUDIT_LOG`) — full name, email, address, the complete card number and CVV, and a freshly re-rendered snapshot of the checkout page HTML (a few KB per entry) — meant to let fraud-review staff look up recent transactions without a database round trip.

The intended design is a bounded ring buffer (e.g. the last 500 transactions), but the shipped code never trims the list, so it grows without bound for as long as the flag stays enabled. At the traffic levels this lab's traffic generator produces, each `payment-app` replica's memory grows by roughly 2-3 MB per minute — clearly visible within a few minutes on the `fivepercent_payment_audit_log_entries` gauge or the container's own memory usage, and enough to hit the Deployment's 256Mi memory limit and get OOMKilled within roughly an hour if left running.

This exists so an instructor can flip the flag live to simulate an in-memory cache that was supposed to be bounded and wasn't — an exercise in noticing unbounded memory growth from the outside (via metrics) and then using a heap profiler to identify the actual retained objects (a giant list of transaction dicts holding full card numbers, CVVs, and re-rendered HTML) as the culprit. Disabling the flag stops further growth immediately but does not free memory already retained by past requests; only a pod restart reclaims it.

Storing the raw card number and CVV in this buffer is itself a second, independent problem beyond the memory leak — a realistic detail, since forgetting to reuse existing redaction logic (like `card_last4` in the structured logs) when adding a new internal-only data path is a common way this kind of mistake actually happens.

For the actual heap-profiling procedure — building the debug image, safely swapping the running Deployment to it, capturing a memray flamegraph, and resetting everything afterward — see the [Heap Profiling Playbook](heap-profiling-playbook.md).

## Connecting To Unleash

The app connects to Unleash using these environment variables:

- `UNLEASH_URL` — the Unleash Client API base URL (e.g. `http://unleash.feature-flags.svc.cluster.local:4242/api`).
- `UNLEASH_API_TOKEN` — a backend/client API token, passed as the `Authorization` header value.
- `UNLEASH_APP_NAME` — the app name reported to Unleash (defaults to `payment-app`).

If `UNLEASH_URL` or `UNLEASH_API_TOKEN` is unset, or the Unleash server is unreachable at startup, the app logs a warning and the flag simply defaults to disabled — the app does not fail to start. This makes Unleash a fully optional dependency for local development.
