# Logging With Loki

## Purpose

This appendix provides a deeper explanation of where direct container logs, the collector, Loki, and Grafana fit in the logging pipeline.

It complements the theory and executable runbook with more detail on each component's role.

## Learning Path

1. Read [Fundamentals 10: Logging](../fundamentals/10-logging-fundamentals.md) for the logging mental model.

2. Run [Optional Logging Lab](../runbooks/optional-logging-lab.md) for the canonical inspection, installation, LogQL query, and cleanup procedure.

3. Use this appendix to understand the component boundaries in more detail.

## Mental Model

Metrics answer numeric questions over time.

Logs answer event and detail questions for specific moments.

Loki stores labeled log streams and serves LogQL queries once a collector sends logs to it.

## What Is Included

The optional Helmfile installs the pinned Loki chart and the pinned Grafana Alloy chart in the `logging` namespace.

`infrastructure/kubernetes/helm-values/kube-prometheus-stack-values.yaml` declares a **Loki** entry under `grafana.additionalDataSources`, in the same file and alongside the existing **Prometheus** and **Alertmanager** data sources (configured via `grafana.sidecar.datasources`). The chart renders all three into one generated `kube-prometheus-stack-grafana-datasource` `ConfigMap`, so Grafana already has a working Loki data source once `make monitoring-up` has run — no separate command is needed, and logs can be explored in Grafana's Explore view instead of only through Loki's HTTP API directly.

Loki runs in single-binary mode with one replica, filesystem storage, and an ephemeral `emptyDir` for its working data. No persistent volume is used.

Alloy runs as a `DaemonSet` and uses the Kubernetes API to discover every pod on the cluster and tail its container logs, so it needs no privileged host-path mounts.

```text
infrastructure/kubernetes/helmfile-loki.yaml
  -> grafana/loki chart -> logging namespace -> single Loki StatefulSet
  -> grafana/alloy chart -> logging namespace -> Alloy DaemonSet (log collector)
```

The Alloy configuration lives in `infrastructure/kubernetes/helm-values/alloy-values.yaml` as an embedded Alloy configuration (the River-style syntax Alloy uses):

- `discovery.kubernetes` discovers every pod on the cluster through the Kubernetes API.

- `discovery.relabel` copies bounded pod metadata (`namespace`, `pod`, `container`, and the `app.kubernetes.io/name` label as `app`) onto the log stream.

- `loki.source.kubernetes` tails each discovered container's logs through the Kubernetes API.

- `loki.write` pushes the resulting log streams to `http://loki.logging.svc.cluster.local:3100/loki/api/v1/push`.

The storage is ephemeral. Removing the release or deleting the kind cluster removes its local data.

## What Is Not Included

Alloy is scoped to Kubernetes pod logs only. It does not collect node-level logs, audit logs, or logs from processes outside a container.

The label set attached to each stream is intentionally small (`namespace`, `pod`, `container`, `app`). Anything else useful for an investigation — status codes, routes, request identifiers — stays in the unindexed log line and must be queried with LogQL line filters or parsers rather than as a Loki label.

## Pipeline Boundaries

The implemented path is:

```text
sample app -> container stdout and stderr -> Kubernetes API (pod logs)
  -> Alloy (discovery.kubernetes, loki.source.kubernetes) -> Loki -> Grafana Explore (LogQL)
```

`kubectl logs` reads the same underlying container log data directly and remains useful for a quick, ad hoc check without querying Loki.

## Label Design

Loki indexes labels rather than the full contents of every log line.

Alloy attaches bounded labels — namespace, pod, container, and app — before sending a stream.

Unbounded values such as request identifiers, IP addresses, or free-form messages should remain in the log content instead of becoming stream labels.

This distinction matters because every unique label set creates a separate stream, and unbounded label values can create unbounded numbers of streams.

## Design Questions

- Which events require logs rather than metrics?

- Which bounded labels are needed to find a workload's logs?

- Which values must remain in the log body and be queried with LogQL filters instead?

- How long would local ephemeral storage be useful for the exercise?

- Which component owns collection, storage, and visualization?

## Validation And Cleanup

Use the [Optional Logging Lab validation and cleanup](../runbooks/optional-logging-lab.md#validation) as the executable source of truth.

The required final state is a functioning direct `kubectl logs` path, a working Alloy-to-Loki ingestion path validated with a LogQL query, and both removed after the exercise.
