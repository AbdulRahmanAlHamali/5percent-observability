# 10: Logging Fundamentals

## Purpose

This chapter explains how logs complement metrics and states the exact logging boundary of the local lab.

> **Important:** The application writes logs that `kubectl logs` can read directly, and the optional exercise also installs Grafana Alloy as a log collector so those same logs are ingested into Loki and become queryable with LogQL.

## Prerequisites

- Understand that metrics summarize numeric behavior over time.

- Know that the sample application runs in Kubernetes on local `kind`.

- Be familiar with the difference between producing, collecting, storing, and querying telemetry.

## Learning Objectives

By the end of this chapter, you should be able to:

- Explain what logs are useful for.

- Describe how logs complement metrics during an investigation.

- Identify the difference between direct pod-log access and centralized logging.

- Explain why installing Loki alone does not make application logs queryable in Loki, and what a collector adds.

- Propose safe, structured fields without exposing sensitive data.

## Core Explanation

Logs are timestamped event records produced by an application or platform component.

They help engineers investigate specific events after a metric or alert identifies a symptom.

Metrics are efficient for trends and aggregation, while logs provide event-level context.

### The Logging Path

A complete centralized logging path needs several stages.

The application must emit logs, a collector must read them, a transport must send them, a backend must store and index them, and a query tool must retrieve them.

Removing any required stage breaks the end-to-end path.

```mermaid
flowchart LR
  app["Sample application<br>Writes stdout logs"] --> runtime["Container runtime<br>Retains pod logs"]
  runtime --> kubectl["kubectl logs<br>Direct local inspection"]
  runtime --> collector["Alloy<br>Tails pod logs via the Kubernetes API"]
  collector --> loki["Loki<br>Stores labeled streams"]
  loki --> query["LogQL<br>Query stored logs"]
```

In this lab, both paths work: `kubectl logs` gives fast direct inspection, while Alloy ships the same logs into Loki for centralized LogQL queries.

Installing Loki alone only provides a backend; Alloy is the collector stage that actually sends container logs to it.

### Useful Log Content

A useful application log records enough context to understand an event without exposing secrets or personal data.

Common safe fields include a timestamp, severity, component, route template, status category, and sanitized request identifier.

Logs should avoid credentials, tokens, raw request bodies, and unnecessary personal information.

A tiny illustrative structured event might look like:

```json
{"level":"info","event":"request_completed","route":"/work","status":200}
```

This snippet illustrates fields only.

The current sample application uses standard Python and Flask log output rather than this exact JSON format.

### Logs During Investigation

A practical investigation often starts with a broad metric symptom, narrows the affected time and component, and then inspects logs for event details.

Logs do not replace metrics because searching all events is inefficient for many trend questions.

Metrics do not replace logs because an aggregate cannot explain every failure.

```mermaid
flowchart TD
  symptom["Metric or alert<br>Identify time and impact"] --> narrow["Narrow scope<br>Component, route, and period"]
  narrow --> logs["Inspect available logs<br>Look for relevant events"]
  logs --> evidence["Build evidence<br>Correlate without assuming causation"]
  evidence --> decision["Decide next step<br>Fix, instrument, or observe"]
```

## Example From This Lab

The Flask application writes request and runtime output to standard output.

Kubernetes makes that output available through `kubectl logs`, so direct local inspection works.

The optional logging lab installs Loki in single-binary mode with local filesystem storage settings, and installs Grafana Alloy as a `DaemonSet` that discovers pods through the Kubernetes API and tails their container logs.

Alloy attaches bounded labels (`namespace`, `pod`, `container`, `app`) and pushes each stream to Loki, so application logs become queryable with LogQL soon after they are written.

This lab validates ingestion by querying Loki's API directly rather than provisioning a Grafana Loki data source, so learners should still treat the Grafana-side query experience as a follow-up design topic.

## Common Mistakes

- Assuming that installing Loki alone (without Alloy) collects Kubernetes logs.

- Claiming an end-to-end logging pipeline works after validating only the Loki pod, without a LogQL query that actually returns ingested log lines.

- Logging secrets, tokens, request bodies, or personal data.

- Using unbounded free-form messages when stable fields would make investigation easier.

- Treating logs as the only monitoring signal.

- Assuming temporal correlation proves that one event caused another.

- Forgetting that direct pod logs may be harder to use after pod replacement or across many replicas.

## Demo Checkpoint

Use [Checkpoint: Inspect logs and Loki boundaries](../runbooks/optional-logging-lab.md#checkpoint-inspect-logs-and-loki-boundaries) and [Checkpoint: Query ingested logs with LogQL](../runbooks/optional-logging-lab.md#checkpoint-query-ingested-logs-with-logql) to verify both the direct log path and the collector-backed Loki path.

## Knowledge Check

1. Which parts of the logging path work end to end in the current lab?

2. Why does a running Loki instance not prove that application logs are stored there without also checking the collector?

3. Which component reads container logs and sends them to Loki in this lab?

4. What information should never be placed in logs?

5. When would you move from a metric to logs during an investigation?

## Related Reading

- [Designing an Observability System](11-designing-an-observability-system.md)

- [Logging with Loki appendix](../appendices/logging-with-loki.md)

- [Observability lab architecture](../architecture.md)

- [Sample application](../../app/README.md)
