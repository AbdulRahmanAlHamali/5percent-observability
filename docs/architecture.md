# Observability Lab Architecture

## Purpose

This document explains the local architecture for the 5percent observability lab.

The lab keeps platform setup, application workload, dashboards, and optional appendices separated so each teaching phase can be run independently.

## Component Topology

```mermaid
flowchart TD
  makefile["Makefile<br>learner entrypoint"] --> kind["kind cluster<br>fivepercent-observability"]
  makefile --> helmfile["Helmfile<br>platform charts"]
  makefile --> kustomize["Kustomize<br>workload resources"]

  helmfile --> kps["kube-prometheus-stack<br>monitoring namespace"]
  kps --> prometheus["Prometheus<br>metrics storage and query"]
  kps --> grafana["Grafana<br>dashboards"]
  kps --> alertmanager["Alertmanager<br>alert routing"]
  kps --> grafanaDatasources["Grafana data sources<br>grafana.additionalDataSources"]
  grafanaDatasources --> grafana

  kustomize --> app["sample metrics app<br>fivepercent-observability namespace"]
  app --> metrics["/metrics<br>Prometheus format"]
  kustomize --> serviceMonitor["ServiceMonitor<br>scrape contract"]
  serviceMonitor --> prometheus
  prometheus --> grafana

  kustomize --> dashboard["Grafana dashboard ConfigMap<br>grafana_dashboard=1"]
  dashboard --> grafana

  kustomize --> rule["PrometheusRule<br>sample alerts"]
  rule --> prometheus
  prometheus --> alertmanager

  helmfile --> loki["optional Loki<br>logging namespace"]
  helmfile --> alloy["optional Alloy<br>logging namespace"]
  app --> podlogs["container stdout<br>Kubernetes pod logs"]
  podlogs --> alloy
  alloy --> loki
  grafanaDatasources -.-> loki
```

## Runtime Flow

```mermaid
sequenceDiagram
  participant Learner
  participant Make as Makefile
  participant Kind as kind
  participant Helmfile
  participant Kubernetes
  participant Prometheus
  participant Grafana

  Learner->>Make: make kind-up
  Make->>Kind: create local cluster
  Learner->>Make: make monitoring-up
  Make->>Helmfile: sync kube-prometheus-stack
  Helmfile->>Kubernetes: install Prometheus, Grafana, Alertmanager
  Helmfile->>Grafana: provision Prometheus, Alertmanager, and Loki data sources
  Learner->>Make: make app-up
  Make->>Kubernetes: build, load, and apply sample app manifests
  Kubernetes->>Prometheus: ServiceMonitor exposes scrape configuration
  Prometheus->>Kubernetes: scrape /metrics on sample app pods
  Learner->>Make: make dashboard-up
  Make->>Kubernetes: apply Grafana dashboard ConfigMap
  Grafana->>Prometheus: query fivepercent_* metrics
```

```mermaid
sequenceDiagram
  participant Learner
  participant Make as Makefile
  participant Helmfile
  participant Kubernetes
  participant Alloy
  participant Loki

  Learner->>Make: make logging-up
  Make->>Helmfile: sync loki, then alloy
  Helmfile->>Kubernetes: install Loki StatefulSet and Alloy DaemonSet
  Alloy->>Kubernetes: discover pods and tail container logs via the API
  Alloy->>Loki: push labeled log streams
  Learner->>Loki: LogQL query via port-forward or Grafana Explore
```

The Grafana **Loki** data source used by Explore in the second diagram is not created here; it already exists once `make monitoring-up` has run, as shown in the first diagram.

## Learning And Documentation Flow

The documentation separates conceptual explanation from executable operations while keeping each topic linked to an observable checkpoint.

```mermaid
flowchart LR
  architecture["Architecture<br>components and boundaries"] --> fundamentals["Fundamentals<br>ordered theory"]
  fundamentals --> checkpoint["Core runbook checkpoints<br>local evidence"]
  checkpoint --> design["Observability design<br>apply the concepts"]
  design --> optional["Optional extensions<br>alerting and logging"]
  optional --> appendices["Deep-dive appendices<br>component details"]
```

Start with this architecture document, continue through `docs/fundamentals/README.md`, and execute the linked checkpoints in `docs/runbooks/core-observability-lab.md`.

The optional alerting and logging runbooks come after the core metrics path.

## Boundary Rules

- `Makefile` owns local commands and hides repeated flags from learners.

- `infrastructure/kubernetes/helmfile.yaml` owns Helm chart releases.

- `infrastructure/kubernetes/apps/` owns workload manifests.

- `infrastructure/kubernetes/dashboards/` owns Grafana dashboard provisioning.

- `infrastructure/kubernetes/helm-values/kube-prometheus-stack-values.yaml` owns Grafana data source provisioning, including the optional Loki data source.

- `infrastructure/kubernetes/alerts/` owns Prometheus alert rules.

- `app/` owns the sample HTTP service and its metrics.

- `docs/fundamentals/` owns theoretical explanations and knowledge checks.

- `docs/runbooks/` owns executable procedures, expected outcomes, validation, troubleshooting, and cleanup.

- `docs/appendices/` owns deeper optional explanations that are not required for the core metrics path.

## Chart Compatibility

The monitoring stack pins `kube-prometheus-stack` chart `87.10.1`, which was the latest public chart release found in the Prometheus Community chart metadata on 2026-07-08.

The optional logging appendix pins Grafana Loki chart `6.55.0` and Grafana Alloy chart `1.11.1`, both from `https://grafana.github.io/helm-charts`.

The public Loki migration documentation identifies the `6.55.0` Loki chart as the final Grafana-repo Loki chart family before the community-chart migration path.

## Resource Model

The lab uses memory limits and CPU requests only.

This keeps the manifests compatible with the workspace Kubernetes rule that forbids CPU limits.
