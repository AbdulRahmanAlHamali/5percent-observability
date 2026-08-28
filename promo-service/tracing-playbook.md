# Promo Service Tracing Playbook

Instructor reference for the promo-service N+1 exercise. The service ships
with auto-instrumentation only; a slow trace ends at an opaque ~560ms
`POST /evaluate`. Students add the missing spans themselves.

All edits are pre-written as numbered comments — find them with:

```bash
grep -rn "TRACING STEP" promo-service/
```

## Steps

1. **Arm the bug** — Unleash (localhost:4242, admin/unleash4all) → enable
   `promo-rule-lookup-misconfigured` in `development`. Apps poll every 15s.

2. **Look at checkout traces** — Grafana → Explore → Tempo:
   `{ span.http.route = "/checkout" }`
   Durations are bimodal: most a few ms, a minority ~560ms.

3. **Narrow to the slow ones** — add the duration filter:
   `{ span.http.route = "/checkout" && duration > 500ms }`
   Slow traces are 3 spans; no attribute says which requests or why.

4. **Apply TRACING STEP 1–5** — each comment block names the active lines
   it replaces; uncomment, delete the replaced lines:
   - STEP 1 `requirements.txt` — sqlite3 auto-instrumentation (db spans)
   - STEP 2 `src/main.py` — the tracer
   - STEP 3 `evaluate()` — `resolve_code` span, `promo.code` attribute
   - STEP 4 `fetch_rule()` — the fan-out span
   - STEP 5 `fetch_rules_batch()` — fast-path contrast span

5. **Redeploy**:
   ```bash
   ./scripts/redeploy-promo-service.sh
   ```

6. **Re-trace** — rerun the step-3 query (search lags ingestion ~1min).
   Slow trace: `resolve_code {promo.code=VIP20, rule_count=35}` +
   35 × `fetch_rule` ~15ms, each with a `SELECT` db span. Fast trace
   (`duration < 100ms`): one `fetch_rules_batch`.

7. **Resolve** — disable the flag; p99 on the payment dashboard collapses
   within ~5min. Batch path (`fetch_rules_batch`) is the permanent fix.

8. **Reset for next cohort** — `git checkout -- promo-service/`, then
   repeat step 5.

Optional two-cycle pacing: apply STEP 1 alone first — 35 instant SELECTs
separated by unexplained ~15ms gaps ("gaps = uninstrumented work"), then
STEP 2–5 to claim them.
