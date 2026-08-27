# Traffic Generator

## Purpose
This is a small Python worker that continuously drives synthetic checkout traffic against the payment app, so the lab's dashboards, metrics, and logs have something to show without a human clicking through the checkout form by hand.

It has no HTTP surface of its own; it just loops.

## Behavior
Each iteration:

1. `GET /checkout` — mints a fresh `checkout_id` and randomized price, same as a real page load.
2. With a small probability (churn), the session stops here without submitting — simulating someone who loads the checkout page and abandons it.
3. Otherwise, `POST /checkout` — submits that same `checkout_id` and amount back with a randomly chosen country and test card number, mirroring a real form submission. With a very small probability, this submission also includes a `quantity` field set to a large random value, simulating a misbehaving wholesale-integration client that posts directly to this endpoint instead of using the checkout UI (see `payment-app/README.md`'s bulk-order fulfillment section).
4. Sleeps a random delay before the next iteration.

Countries and card numbers are drawn uniformly at random from a fixed list (matching `scripts/generate-checkout-traffic.sh`). The list has one fewer country than a fully realistic set so Syria's traffic share is a little higher than an even split across ten countries would give; with too long a country list, the country-specific fraud-check misconfiguration gets diluted and is hard to see clearly in the dashboards.

Deployed with 5 replicas, so five independent sessions run concurrently.

## Configuration
- `TARGET_URL` — base URL to send checkout traffic to. Defaults to `http://payment-app`, the payment app's own in-cluster Service name, for standalone/local use. The Kubernetes Deployment overrides this to `http://payment-gateway.envoy-gateway-system.svc.cluster.local`, so traffic actually flows through the Envoy Gateway data plane in front of the payment app rather than hitting its Service directly — this is what makes edge-level metrics (request rate, status codes) reflect real generated traffic, the same way a real load balancer or ingress would.
- `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` — random delay range between iterations (defaults `0.2` / `1.5`).
- `REQUEST_TIMEOUT_SECONDS` — per-request timeout (default `5`).
- `CHECKOUT_CHURN_RATE` — probability that a session abandons after `GET /checkout` instead of submitting (default `0.05`, i.e. 5%).
- `BULK_ORDER_RATE` — probability that a submission includes a bulk `quantity` field (default `0.005`, i.e. 0.5%).
- `BULK_ORDER_MIN_QUANTITY` / `BULK_ORDER_MAX_QUANTITY` — range the bulk `quantity` value is drawn from when triggered (defaults `500000` / `2000000`).

A failed request is logged and the loop continues; it does not crash the process, so a transient payment-app restart doesn't take the generator down with it.

## Deployment
Deployed and torn down together with the payment app itself via `make payment-app-up` / `make payment-app-down` — it has no separate lifecycle, since it exists only to drive traffic into that app.
