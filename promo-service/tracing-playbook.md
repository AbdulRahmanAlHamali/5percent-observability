# Promo Service Tracing Playbook

The promo service ships with auto-instrumentation only: Flask creates one
server span per request and `requests` propagates trace context from the
payment app. Its internals — code resolution and rule fetching — are
invisible to the trace. This playbook adds that visibility incrementally.

Use it after the metrics investigation has narrowed the problem to slow
`POST /checkout` requests and the trace shows an opaque `POST /evaluate`
span carrying almost all of the time.

## The wall this playbook breaks

With the `promo-rule-lookup-misconfigured` flag enabled, a slow checkout
trace contains only:

```
payment-app     POST /checkout      ~570ms
payment-app     POST (client)       ~569ms
promo-service   POST /evaluate      ~565ms      <- opaque
```

The trace says promo-service is slow and nothing else. Which requests are
affected and where the time goes are both unanswerable: the affected
segment (the promo code) appears in no metric label and no log field, and
the service's internal phases have no spans.

A gap or an opaque span in a trace is uninstrumented work, not idle time.
The fix is to claim that time with spans.

## The steps

Every step is marked in the source with a numbered comment. Search for
`TRACING STEP` across `promo-service/` to find them all:

- `TRACING STEP 1` — `requirements.txt`: enable
  `opentelemetry-instrumentation-sqlite3`. Every SQLite query then produces
  a db span with the SQL in `db.statement`, with no code changes.
- `TRACING STEP 2` — `src/main.py`: create the module's `tracer`.
- `TRACING STEP 3` — `src/main.py`, `evaluate()`: wrap code resolution in a
  `resolve_code` span and record `promo.code` and `promo.rule_count` as
  attributes. This is the step that makes the affected segment queryable.
- `TRACING STEP 4` — `src/main.py`, `fetch_rule()`: one span per rule
  fetch, so per-rule cost appears as bars instead of dead time.
- `TRACING STEP 5` — `src/main.py`, `fetch_rules_batch()`: the same for the
  batched path, so fast traces show one wide span for contrast.

Each commented block states exactly which active lines it replaces.
Uncomment the block, delete the lines it replaces, keep indentation.

## Deploy and observe

```bash
make promo-service-build promo-service-load
kubectl --context kind-fivepercent-observability -n payment-checkout rollout restart deployment/promo-service
kubectl --context kind-fivepercent-observability -n payment-checkout rollout status deployment/promo-service
```

Wait a minute or two for new traffic to flow and for Tempo's search index
to catch up (trace-by-id lookup is immediate; search lags ingestion).

In Grafana Explore -> Tempo:

```
{ span.http.route = "/checkout" && duration > 500ms }
```

A slow trace now shows `resolve_code` with `promo.code` and
`promo.rule_count` attributes, and a ladder of `fetch_rule` spans of about
15ms each — one per rule — each containing a `SELECT` db span with the
same parameterized statement. Compare against a fast trace
(`duration < 100ms`): one `fetch_rules_batch` span, one query.

## Suggested pacing

One rebuild cycle: apply steps 1-5 together, deploy once, re-trace. This is
the shortest path to the reveal.

Two rebuild cycles, if time allows: apply only step 1 first. The slow trace
then shows 35 hair-thin `SELECT` spans separated by unexplained ~15ms gaps —
worth sitting with, because "the spans are instant but the request is slow"
is how partially instrumented services actually look. Steps 2-5 then claim
the gaps.

## Reading the result

- The repeated identical `db.statement` is the N+1 signature: the question
  is not "why is this query slow" but "why is it asked 35 times".
- `promo.rule_count` scales with duration across traces; `promo.code`
  names the segment. Neither exists in metrics or logs — adding the promo
  code as a metric label would be a cardinality mistake, and logging it was
  never done. The span attribute is the right home for per-request
  dimensions.
- The batched path already exists in the code (`fetch_rules_batch`); the
  flag chooses between them. Disabling the flag is the incident
  remediation, and the trace-verified before/after is the proof.

## Restore the shipped state

To reset the exercise for the next cohort, revert the uncomments (or
`git checkout -- promo-service/`), rebuild, and redeploy with the same
three commands above.
