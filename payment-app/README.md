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
- `payment_accepted` / `payment_rejected` — emitted on `POST /checkout`. Fields: `checkout_id`, `product`, `amount`, `currency`, `country`, `ip`, `card_last4`, `status`, `rejection_reason` (`null` when accepted), `quantity` (`1` for a normal single-item checkout).
- `bulk_order_manifest_chunk_processed` — emitted while a bulk order (see below) is being fulfilled in the background. Fields: `checkout_id`, `quantity`, `units_processed`.

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

## Feature Flag: Simulated Crash (Unbounded Bulk-Order Fulfillment)

`POST /checkout` also accepts an optional `quantity` field, undocumented and unused by the checkout UI (`checkout.html` has no input for it). It exists because this same endpoint doubles as the intake for a wholesale-integration client that orders in bulk and posts directly to it, bypassing the normal single-item form entirely.

A third boolean Unleash feature flag, `payment-bulk-order-fulfillment-enabled`, gates whether an accepted payment with `quantity > 1` kicks off background fulfillment: a per-unit manifest entry (for a downstream warehouse pick-list export) is appended to an in-memory list, `_FULFILLMENT_MANIFEST`, once for every unit ordered. Nothing checks `quantity` against any upper bound before doing this — a normal wholesale order is a few dozen units at most, but the field is trusted as-is.

Unlike the two flags above, this one isn't meant to be flipped live by an instructor to demonstrate cause and effect. It's enabled once to arm the scenario, and the crash itself is then triggered indirectly and unpredictably: the traffic generator very rarely (`BULK_ORDER_RATE`, default 0.5%) simulates that same misbehaving wholesale client by posting a `quantity` in the hundreds of thousands to a few million. Fulfillment for an order that size means appending that many manifest entries — comfortably enough to exceed the Deployment's 256Mi memory limit on its own, well before the manifest is anywhere near a stable size.

The fulfillment loop processes the manifest in chunks (`BULK_ORDER_CHUNK_SIZE` units at a time, sleeping `BULK_ORDER_CHUNK_DELAY_SECONDS` between chunks) rather than allocating everything at once. This is deliberate: it gives the pod's memory usage a visible ramp over several seconds instead of an instant cliff, and — since this happens in a background thread while the Flask process keeps handling other requests — lets other checkouts' log lines interleave with the `bulk_order_manifest_chunk_processed` events before the pod is OOMKilled. The triggering request itself returns a normal, successful response immediately after starting the background thread, long before the crash; by the time the pod dies, that request's own log line is not the last thing written, and is not obviously connected to the crash without correlating the `quantity` field back to the timing of the memory spike.

This exists as a "how do you debug with limited information" exercise: the pod restarts (visible via `Scrape Targets Up` dropping and a `kubectl get pods` restart count), the gateway's error-rate panel spikes briefly as in-flight requests to the dying pod fail, and the only trail connecting the two is the payment-app memory graph's ramp shape correlated against structured logs from that time window — not a single obvious log line or dashboard counter.

## Connecting To Unleash

The app connects to Unleash using these environment variables:

- `UNLEASH_URL` — the Unleash Client API base URL (e.g. `http://unleash.feature-flags.svc.cluster.local:4242/api`).
- `UNLEASH_API_TOKEN` — a backend/client API token, passed as the `Authorization` header value.
- `UNLEASH_APP_NAME` — the app name reported to Unleash (defaults to `payment-app`).

If `UNLEASH_URL` or `UNLEASH_API_TOKEN` is unset, or the Unleash server is unreachable at startup, the app logs a warning and the flag simply defaults to disabled — the app does not fail to start. This makes Unleash a fully optional dependency for local development.
