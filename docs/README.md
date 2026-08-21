# 5percent Observability Lab Docs

## Purpose

These docs support a hands-on observability session using local Kubernetes, Prometheus, Grafana, Alertmanager, and an optional Loki appendix.

## How To Navigate This Repository

Follow the main learning path in this order:

1. Read [Architecture](architecture.md) to understand the components, ownership boundaries, and metrics flow.

2. Follow the [Fundamentals Learning Path](fundamentals/README.md) for the theoretical topics in order.

3. Execute the [Core Observability Lab](runbooks/core-observability-lab.md) through the checkpoints linked from each fundamentals topic.

4. Use the [Runbook Index](runbooks/README.md) for prerequisite installation and optional alerting or logging labs.

Theory and practice are paired deliberately.

Each fundamentals chapter explains one concept and links to the checkpoint where that concept can be observed in the local lab.

The runbooks are the canonical source for commands, expected outcomes, validation, troubleshooting, and cleanup.

## Documentation Index

### Architecture

- [Architecture](architecture.md) explains the lab topology, runtime sequence, ownership boundaries, chart compatibility, and resource model.

### Theoretical Knowledge

- [Fundamentals Learning Path](fundamentals/README.md) indexes the eleven focused topics from observability basics through observability-system design.

### Practical Runbooks

- [Runbook Index](runbooks/README.md) provides prerequisites, operating boundaries, and the practical learning order.

- [Core Observability Lab](runbooks/core-observability-lab.md) is the canonical metrics demo.

- [Optional Alerting Lab](runbooks/optional-alerting-lab.md) demonstrates reversible alert lifecycle behavior.

- [Optional Logging Lab](runbooks/optional-logging-lab.md) demonstrates direct logs and the Alloy-to-Loki ingestion path, validated with a LogQL query.

### Deeper Appendices

- [Logging With Loki](appendices/logging-with-loki.md) explains the optional logging architecture, its collector, and its label design.

- [Alerting With Alertmanager](appendices/alerting-with-alertmanager.md) explains Prometheus rule evaluation and Alertmanager routing.

### Planning And Validation

- [Session Plan](session-plan.md) provides the phased teaching agenda.

- [Validation](validation.md) lists static and local-cluster checks.

- [Brainstorming](brainstorming.md) preserves the early notes, assumptions, questions, and draft plan.

- [LLM Guidance](llm/README.md) records repository-specific guidance for agents working in this lab.

## Local-Only Boundary

All commands are designed for a local `kind` cluster.

Do not point this lab at a remote Kubernetes cluster unless the session owner explicitly changes the scope.
