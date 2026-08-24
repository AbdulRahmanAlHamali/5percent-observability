# Observability Lab Runbooks

## Purpose

This page is the prerequisite guide and index for the local 5percent observability lab runbooks.

Use the core runbook as the single canonical procedure for the metrics lab.

## Install Prerequisites

The lab can install required local tools on supported operating systems.

This command mutates the local machine, so review the planned commands first.

If `make` is already available, use the Makefile target.

```bash
DRY_RUN=1 make install-prereqs
```

Expected outcome: the installer prints the commands it would run without installing packages.

Run the installer when the dry-run output looks correct.

```bash
make install-prereqs
make check-prereqs
```

If `make` is not available yet, start from the workspace root and run the installer directly, then rerun the Makefile checks.

```bash
cd hape-academy/5percent/observability
DRY_RUN=1 ./scripts/install-prereqs.sh
./scripts/install-prereqs.sh
make check-prereqs
```

Supported environments:

- macOS through Homebrew.

- Ubuntu or Debian through `apt-get`, the current Buildkite-hosted Helm repository, and verified official tool downloads.

- Windows from Git Bash through `winget`, with a Helmfile fallback download when needed.

Installer safety:

- `DRY_RUN=1` prints commands without installing packages.

- Downloaded `kind`, `kubectl`, and `helmfile` binaries are checksum-verified before installation.

- The installer does not access Kubernetes clusters, cloud APIs, SSH hosts, databases, or remote Docker contexts.

Docker notes:

- Docker Desktop on macOS and Windows may require manual startup after installation.

- Docker on Ubuntu or Debian may require logging out and back in after Docker group changes.

- `make check-prereqs` verifies tool binaries, but it does not prove the Docker daemon is running.

- A regular Ubuntu container can validate dependency installation, but it cannot run `kind` unless a usable Docker daemon is configured separately.

## Runbook Index

- [Core Observability Lab](core-observability-lab.md) is the canonical executable metrics path from local setup through dashboard reading and observability design.

- [Optional Alerting Lab](optional-alerting-lab.md) applies the sample alert rules and demonstrates pending, firing, and resolved states.

- [Optional Logging Lab](optional-logging-lab.md) inspects application logs directly and through the Alloy-to-Loki ingestion path, validated with a LogQL query.

## Learning Order

1. Complete [Core Observability Lab](core-observability-lab.md).

2. Complete [Optional Alerting Lab](optional-alerting-lab.md) when you want to explore metric-based alerts.

3. Complete [Optional Logging Lab](optional-logging-lab.md) when you want to compare direct logs with a collector-backed Loki logging pipeline.

The alerting and logging runbooks are independent optional extensions after the core metrics path.

## Operating Boundary

Run all procedures from `hape-academy/5percent/observability`.

The Make targets in these runbooks hard-pin Kubernetes operations to the local `kind-fivepercent-observability` context.

Every direct `kubectl` command also names that context explicitly.

Do not adapt these exercises to another cluster.
