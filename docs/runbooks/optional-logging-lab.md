# Optional Logging Lab

## Purpose

This optional runbook compares direct Kubernetes log inspection with the installed Loki logging pipeline.

Read [Fundamentals 10: Logging](../fundamentals/10-logging-fundamentals.md) for the theory and [Logging With Loki](../appendices/logging-with-loki.md) for the deeper component explanation.

## Prerequisites

- Complete the [Core Observability Lab](core-observability-lab.md) through application deployment.

- Work from `hape-academy/5percent/observability`.

- Keep the local `kind-fivepercent-observability` cluster and sample app running.

- Keep at least 512 MiB of local cluster memory available for the Loki and Alloy container limits.

Verify that the app pods are ready.

```bash
kubectl --context kind-fivepercent-observability -n fivepercent-observability get pods -l app.kubernetes.io/name=sample-metrics-app
```

Expected outcome: two sample app pods report `Running` and ready.

## Checkpoint: Inspect Logs And Loki Boundaries

Inspect recent application logs directly through the Kubernetes API.

```bash
kubectl --context kind-fivepercent-observability -n fivepercent-observability logs -l app.kubernetes.io/name=sample-metrics-app --all-containers=true --tail=50 --prefix=true
```

Expected outcome: the output contains startup or HTTP request records from the sample app pods.

Explanation: `kubectl logs` reads container stdout and stderr for selected pods and is sufficient for a small local inspection.

It does not provide a central historical query path across changing pods.

If you need fresh request records, expose the app in terminal 1.

```bash
kubectl --context kind-fivepercent-observability -n fivepercent-observability port-forward service/sample-metrics-app 8080:80
```

In terminal 2, call the app, then repeat the `kubectl logs` command.

```bash
curl http://localhost:8080/
curl http://localhost:8080/work
```

Leave the app port-forward running; the next checkpoint reuses it to generate more traffic.

Install Loki and the Alloy log collector through the local Helmfile target, then load the Grafana Loki data source through the sidecar.

```bash
make logging-up
make datasource-up
```

Inspect the installed resources and wait for the Loki StatefulSet and the Alloy DaemonSet.

```bash
kubectl --context kind-fivepercent-observability -n logging get statefulsets,daemonsets,pods,services
kubectl --context kind-fivepercent-observability -n logging rollout status statefulset/loki --timeout=5m
kubectl --context kind-fivepercent-observability -n logging rollout status daemonset/alloy --timeout=5m
```

Expected outcome: the `loki` StatefulSet and the `alloy` DaemonSet both reach their ready state in the `logging` namespace.

Explanation: this lab installs Loki in single-binary mode with local filesystem storage and no persistent volume, and Alloy as a `DaemonSet` that discovers pods through the Kubernetes API and tails their container logs.

The pipeline is:

```text
sample app stdout -> kubectl logs
sample app stdout -> Kubernetes API -> Alloy -> Loki
```

## Checkpoint: Query Ingested Logs With LogQL

Generate fresh traffic so there is something recent to find.

```bash
curl http://localhost:8080/
curl http://localhost:8080/work
curl http://localhost:8080/work
```

In terminal 3, expose Loki on local port `3100`.

```bash
kubectl --context kind-fivepercent-observability -n logging port-forward svc/loki 3100:3100
```

In terminal 4, query Loki directly with LogQL for the sample app's stream.

```bash
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={namespace="fivepercent-observability", app="sample-metrics-app"}' \
  --data-urlencode 'limit=20'
```

Expected outcome: the response contains `"status": "success"` and a non-empty `result` array with recent request log lines from both app pods.

Explanation: `discovery.kubernetes` and `loki.source.kubernetes` in Alloy's configuration (`infrastructure/kubernetes/helm-values/alloy-values.yaml`) discover every pod on the cluster and tail its container logs through the Kubernetes API. `discovery.relabel` attaches the `namespace`, `pod`, `container`, and `app` labels used above. `loki.write` pushes the resulting streams to Loki.

Filter to one pod's stream, or filter the log body with a LogQL line filter.

```bash
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={namespace="fivepercent-observability", app="sample-metrics-app"} |= "/work"' \
  --data-urlencode 'limit=20'
```

Expected outcome: only log lines mentioning `/work` are returned, demonstrating that unindexed request detail (the route) lives in the log body rather than as a Loki label.

Validation: identify which fields are Loki labels (`namespace`, `pod`, `container`, `app`) versus which fields only exist inside the log line and require a LogQL filter to find.

Stop the app and Loki port-forwards with `Ctrl-C` when this checkpoint is complete.

## Checkpoint: Explore Logs In Grafana

In terminal 3, expose Grafana on local port `3000`.

```bash
make grafana-port-forward
```

Open `http://localhost:3000`, sign in, and open **Explore**.

Select the **Loki** data source and run the same query used above.

```logql
{namespace="fivepercent-observability", app="sample-metrics-app"}
```

Expected outcome: Explore renders matching log lines and a log-volume histogram over the selected time range.

Explanation: `make datasource-up` applies `infrastructure/kubernetes/datasources/loki-datasource.yaml`, a `ConfigMap` labeled `grafana_datasource=1` that the Grafana sidecar picks up and provisions as a data source pointed at `http://loki.logging.svc.cluster.local:3100`. Grafana's Explore view sends the same LogQL query through this data source rather than through a direct `curl` to Loki's API.

Validation: confirm the **Loki** data source appears under Grafana's data source list and that its connection test succeeds.

## Validation

Confirm the direct log path still works.

```bash
kubectl --context kind-fivepercent-observability -n fivepercent-observability logs -l app.kubernetes.io/name=sample-metrics-app --all-containers=true --tail=10 --prefix=true
```

Confirm the Loki and Alloy workload status, and that the Grafana data source ConfigMap is present.

```bash
kubectl --context kind-fivepercent-observability -n logging get statefulset loki
kubectl --context kind-fivepercent-observability -n logging get daemonset alloy
kubectl --context kind-fivepercent-observability -n logging get pods
kubectl --context kind-fivepercent-observability -n monitoring get configmap loki-datasource --show-labels
```

Expected outcome: direct app logs are readable, Loki is ready, Alloy is ready on every node, a LogQL query against `{namespace="fivepercent-observability", app="sample-metrics-app"}` returns recent entries, and the `loki-datasource` ConfigMap has `grafana_datasource=1`.

## Troubleshooting

If direct logs are empty, generate a request and select the pods again.

```bash
kubectl --context kind-fivepercent-observability -n fivepercent-observability get pods -l app.kubernetes.io/name=sample-metrics-app
kubectl --context kind-fivepercent-observability -n fivepercent-observability logs -l app.kubernetes.io/name=sample-metrics-app --all-containers=true --tail=50 --prefix=true
```

If Loki does not become ready, inspect the StatefulSet, pod status, and namespace events.

```bash
kubectl --context kind-fivepercent-observability -n logging describe statefulset loki
kubectl --context kind-fivepercent-observability -n logging get pods
kubectl --context kind-fivepercent-observability -n logging get events --sort-by=.lastTimestamp
```

If a `loki-0` pod is stuck in `CrashLoopBackOff` reporting a read-only filesystem error, delete the pod so the `StatefulSet` recreates it on the current pod template; a change to `loki-values.yaml` does not always trigger an automatic rolling replacement of an already-crashing pod.

```bash
kubectl --context kind-fivepercent-observability -n logging delete pod loki-0
```

If the Alloy `DaemonSet` is not ready, inspect its pods and logs for configuration errors.

```bash
kubectl --context kind-fivepercent-observability -n logging get pods -l app.kubernetes.io/name=alloy
kubectl --context kind-fivepercent-observability -n logging logs -l app.kubernetes.io/name=alloy -c alloy --tail=50
```

If a LogQL query returns an empty `result` array, confirm traffic was generated after Alloy became ready, and confirm the label values match the running app's namespace and `app.kubernetes.io/name` label exactly.

```bash
curl -s "http://localhost:3100/loki/api/v1/label/app/values"
curl -s "http://localhost:3100/loki/api/v1/label/namespace/values"
```

If Grafana's Explore view has no **Loki** data source in the dropdown, confirm `make datasource-up` ran and check the ConfigMap and sidecar.

```bash
kubectl --context kind-fivepercent-observability -n monitoring get configmap loki-datasource --show-labels
kubectl --context kind-fivepercent-observability -n monitoring logs -l app.kubernetes.io/name=grafana -c grafana-sc-datasources --tail=20
```

If the **Loki** data source appears but its connection test fails, confirm Loki itself is ready; the data source's URL depends on the `loki` Service existing in the `logging` namespace.

## Cleanup

Remove the Grafana data source, then Loki and Alloy.

```bash
make datasource-down
make logging-down
```

Expected outcome: the `loki-datasource` ConfigMap and the Loki and Alloy Helm releases and workloads are removed from the local cluster.

The `logging` namespace may remain empty after the Helm releases are removed.

Verify that the Loki StatefulSet, the Alloy DaemonSet, and the data source ConfigMap are absent.

```bash
kubectl --context kind-fivepercent-observability -n logging get statefulset loki
kubectl --context kind-fivepercent-observability -n logging get daemonset alloy
kubectl --context kind-fivepercent-observability -n monitoring get configmap loki-datasource
```

Expected outcome: Kubernetes reports that all three resources are not found.

This cleanup does not remove the core metrics lab.
