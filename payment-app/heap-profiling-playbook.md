# Heap Profiling Playbook

## Purpose

This is the step-by-step procedure for capturing a real heap profile (a memray flamegraph) from a running `payment-app` pod, without restarting the process you're actually trying to inspect any more than necessary.

It exists to investigate memory growth — most concretely, the `payment-audit-log-misconfigured` feature flag described in the main [README](README.md), which causes an unbounded in-memory transaction buffer to grow forever once enabled. The same procedure applies to any future memory issue in this app.

## Why This Isn't Simpler

`kubectl debug` with a separate ephemeral debug container looks like the obvious tool for this, but it structurally cannot run memray's `attach` command: memray attach works by having the *target process itself* `dlopen()` a shared library, and that library only exists in the debugging container's own filesystem. Since every container has its own separate root filesystem in Kubernetes, the target process can never see that file, no matter what capabilities the debug container is granted. `ps`, `gdb`-based inspection, `strace`, and `lsof` all work fine cross-container; memray's attach mechanism specifically does not.

The reliable path is to run the profiling tools in the *same* container as the app, which means temporarily swapping the running pod to a debug-tooled build of the exact same image.

## Step 1: Build And Load The Debug Image

`payment-app/Dockerfile` is a multi-stage build. The `runtime` stage (the default, what's normally deployed) is unmodified. The `debug` stage is built on top of it and adds `procps`, `gdb`, `strace`, `lsof`, `memray`, and `py-spy`.

```bash
make payment-app-debug-build
make payment-app-debug-load
```

This tags the image `fivepercent-observability-payment-app:local-debug` and loads it onto every kind node. Skip this step if you've already done it and haven't changed `payment-app/` since.

## Step 2: Switch The Deployment To The Debug Image

Two changes are required together, in a single patch — not two separate ones, since each `kubectl patch` triggers its own rolling restart, and every restart resets this app's in-memory state back to zero:

- The image, swapped to the debug tag.
- `securityContext.capabilities.add: ["SYS_PTRACE"]` **and** `securityContext.runAsUser: 0`.

Both are needed together. Capabilities added via `securityContext` land in a non-root process's *bounding* capability set but not its *effective* set — nothing here raises them to *ambient*, so a non-root process can't actually use `SYS_PTRACE` even though it's technically been granted. Running as root is what makes the granted capability usable.

```bash
kubectl --context kind-fivepercent-observability -n payment-checkout patch deployment payment-app --type=json -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/image","value":"fivepercent-observability-payment-app:local-debug"},
  {"op":"add","path":"/spec/template/spec/containers/0/securityContext","value":{"runAsUser":0,"capabilities":{"add":["SYS_PTRACE"]}}}
]'
kubectl --context kind-fivepercent-observability -n payment-checkout rollout status deployment/payment-app --timeout=90s
```

This restarts every replica. Note the resulting pod name(s):

```bash
kubectl --context kind-fivepercent-observability -n payment-checkout get pods -l app.kubernetes.io/name=payment-app
```

Expected outcome: two new pods running, ready.

## Step 3: Generate Something Worth Profiling

Restarting reset whatever had already leaked. If you're investigating the audit log specifically, re-enable the flag (see the README for the Unleash login flow) and let the traffic generator's 5 replicas rebuild real leak state — a couple of minutes is plenty; you can watch it via `fivepercent_payment_audit_log_entries` on the `/metrics` endpoint or the payment-app Grafana dashboard.

If you're investigating something else, just make sure the code path you care about is actually running under load before you attach.

## Step 4: Attach memray And Capture

The app runs as PID 1 in its container (`opentelemetry-instrument` execs into the Python process rather than spawning a child, so there's no wrapper process to work around — this is worth reconfirming with `cat /proc/1/cmdline` if the entrypoint ever changes).

Pick one pod and attach for a fixed duration:

```bash
POD=<pod-name>
NS=payment-checkout
kubectl --context kind-fivepercent-observability -n "$NS" exec "$POD" -- \
  memray attach --duration 30 --output /tmp/leak.bin --force 1
```

`attach` returns immediately and tracks in the background for the given duration (seconds). Wait at least that long before moving on.

## Step 5: Generate The Flamegraph

```bash
kubectl --context kind-fivepercent-observability -n "$NS" exec "$POD" -- \
  memray flamegraph --leaks --no-web -o /tmp/leak_flamegraph.html -f /tmp/leak.bin
```

- `--leaks` is essential — without it you get *all* allocation activity for the window, dominated by ordinary request-handling churn (Werkzeug buffers, OpenTelemetry span encoding) that gets freed immediately. `--leaks` shows only what's still retained and unfreed at the end of the capture, which is what you actually want when hunting a leak.
- `--no-web` bundles the viewer's JS directly into the HTML file instead of referencing a CDN, so the file is fully self-contained and viewable offline once copied out.

## Step 6: Copy The Flamegraph To Your Machine

The file only exists in the container's own ephemeral filesystem — copy it out before doing anything else, including moving on to the reset step.

```bash
kubectl --context kind-fivepercent-observability -n "$NS" cp "$POD:/tmp/leak_flamegraph.html" ./leak_flamegraph.html
open ./leak_flamegraph.html   # macOS; use xdg-open or your file manager elsewhere
```

Reading it: a Python `list` only "allocates" for its own small backing array of pointers — the objects it holds (dicts, rendered HTML strings, etc.) are separate allocations attributed to wherever *they* were created, not to the list or the `.append()` call. Don't look for one big blob at the append call site; look for the individual object-creation call sites instead, and use the flamegraph to trace them back to what's holding a reference to them.

## Step 7: Reset The Deployment

The debug image and the elevated `securityContext` should not be left running any longer than needed. This takes **two** steps, not one — `make payment-app-up` alone is not enough:

```bash
make payment-app-up
```

`kubectl apply`'s 3-way merge reverts the image correctly, since that field is tracked in `last-applied-configuration`. It will **not** remove the `securityContext` block, though — that was added with a raw `kubectl patch` in Step 2, which bypasses `last-applied-configuration` entirely, so `apply` has no record that the field should be deleted and silently leaves it in place. Confirmed by testing this directly: after `make payment-app-up`, the image was back to `:local` but `securityContext` still showed `{"capabilities":{"add":["SYS_PTRACE"]},"runAsUser":0}`.

Remove it explicitly:

```bash
kubectl --context kind-fivepercent-observability -n payment-checkout patch deployment payment-app --type=json -p='[
  {"op":"remove","path":"/spec/template/spec/containers/0/securityContext"}
]'
kubectl --context kind-fivepercent-observability -n payment-checkout rollout status deployment/payment-app --timeout=90s
```

Verify both are actually gone:

```bash
kubectl --context kind-fivepercent-observability -n payment-checkout get deployment payment-app \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}{.spec.template.spec.containers[0].securityContext}{"\n"}'
```

Expected outcome: the image line reads `fivepercent-observability-payment-app:local`, and the `securityContext` line is empty.
