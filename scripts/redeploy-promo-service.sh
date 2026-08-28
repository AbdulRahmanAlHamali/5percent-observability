#!/usr/bin/env bash
# Rebuild the promo service image, load it into kind, and restart the
# deployment so pods pick it up (the :local tag never changes, so a
# rebuild alone does not roll pods).
set -euo pipefail

cd "$(dirname "$0")/.."
kind_context="kind-fivepercent-observability"

make promo-service-build promo-service-load
kubectl --context "${kind_context}" -n payment-checkout rollout restart deployment/promo-service
kubectl --context "${kind_context}" -n payment-checkout rollout status deployment/promo-service --timeout=180s
