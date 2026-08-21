override KIND_CLUSTER_NAME := fivepercent-observability
override KIND_CONTEXT := kind-fivepercent-observability
KIND_CONFIG_PATH ?= infrastructure/kubernetes/kind/cluster-config.yaml
HELMFILE_PATH ?= infrastructure/kubernetes/helmfile.yaml
LOGGING_HELMFILE_PATH ?= infrastructure/kubernetes/helmfile-loki.yaml
override KUBECTL := kubectl --context "$(KIND_CONTEXT)"
APP_IMAGE ?= fivepercent-observability-sample-app:local
APP_NAMESPACE ?= fivepercent-observability
GRAFANA_PORT ?= 3000
PROMETHEUS_PORT ?= 9090
ALERTMANAGER_PORT ?= 9093
KUSTOMIZE_TARGET_PATH := $(word 2,$(MAKECMDGOALS))

.PHONY: help install-prereqs check-prereqs ensure-kind-context kind-up kind-down monitoring-up monitoring-down logging-up logging-down app-build app-load app-up app-down dashboard-up dashboard-down alerts-up alerts-down grafana-port-forward prometheus-port-forward alertmanager-port-forward status clean kustomize-apply kustomize-delete

ifneq ($(filter kustomize-apply kustomize-delete,$(firstword $(MAKECMDGOALS))),)
  ifneq ($(KUSTOMIZE_TARGET_PATH),)
$(eval $(KUSTOMIZE_TARGET_PATH):;@:)
  endif
endif

help: ## Show available commands.
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | \
	awk -F ':.*?## ' '{printf "%-24s %s\n", $$1, $$2}' | \
	sort

check-prereqs: ## Check required local tools.
	./scripts/check-prereqs.sh

install-prereqs: ## Install required local tools for supported OSes.
	./scripts/install-prereqs.sh

ensure-kind-context: ## Fail unless kubectl points at this lab's kind context.
	@current_context=$$(kubectl config current-context 2>/dev/null || true); \
	if [ "$$current_context" != "$(KIND_CONTEXT)" ]; then \
		echo "Error: current kubectl context is '$$current_context', expected '$(KIND_CONTEXT)'."; \
		echo "Run: kubectl config use-context $(KIND_CONTEXT)"; \
		exit 1; \
	fi

kind-up: ## Create the local kind cluster.
	@if kind get clusters | grep -xq "$(KIND_CLUSTER_NAME)"; then \
		echo "kind cluster $(KIND_CLUSTER_NAME) is already running"; \
	else \
		kind create cluster --name "$(KIND_CLUSTER_NAME)" --config "$(KIND_CONFIG_PATH)"; \
	fi

kind-down: ## Delete the local kind cluster.
	@if kind get clusters | grep -xq "$(KIND_CLUSTER_NAME)"; then \
		kind delete cluster --name "$(KIND_CLUSTER_NAME)"; \
	else \
		echo "kind cluster $(KIND_CLUSTER_NAME) is not running"; \
	fi

monitoring-up: ensure-kind-context ## Install kube-prometheus-stack.
	helmfile --kube-context "$(KIND_CONTEXT)" -f "$(HELMFILE_PATH)" --selector stack=monitoring sync

monitoring-down: ensure-kind-context ## Remove kube-prometheus-stack.
	@if helm --kube-context "$(KIND_CONTEXT)" -n monitoring status kube-prometheus-stack >/dev/null 2>&1; then \
		helmfile --kube-context "$(KIND_CONTEXT)" -f "$(HELMFILE_PATH)" --selector stack=monitoring destroy; \
	else \
		echo "kube-prometheus-stack release is already absent"; \
	fi

logging-up: ensure-kind-context ## Install optional Loki logging stack.
	helmfile --kube-context "$(KIND_CONTEXT)" -f "$(LOGGING_HELMFILE_PATH)" sync

logging-down: ensure-kind-context ## Remove optional Loki logging stack.
	@if helm --kube-context "$(KIND_CONTEXT)" -n logging status loki >/dev/null 2>&1; then \
		helmfile --kube-context "$(KIND_CONTEXT)" -f "$(LOGGING_HELMFILE_PATH)" destroy; \
	else \
		echo "loki release is already absent"; \
	fi

app-build: ## Build the local sample app image.
	docker build -t "$(APP_IMAGE)" ./app

app-load: ## Load the sample app image into kind.
	kind load docker-image "$(APP_IMAGE)" --name "$(KIND_CLUSTER_NAME)"

app-up: ensure-kind-context app-build app-load ## Deploy the sample metrics app.
	$(MAKE) kustomize-apply infrastructure/kubernetes/apps/sample-metrics-app

app-down: ensure-kind-context ## Delete the sample metrics app.
	$(MAKE) kustomize-delete infrastructure/kubernetes/apps/sample-metrics-app

dashboard-up: ensure-kind-context ## Load Grafana dashboards through the sidecar.
	$(MAKE) kustomize-apply infrastructure/kubernetes/dashboards

dashboard-down: ensure-kind-context ## Remove Grafana dashboard ConfigMaps.
	$(MAKE) kustomize-delete infrastructure/kubernetes/dashboards

alerts-up: ensure-kind-context ## Apply sample Prometheus alert rules.
	$(MAKE) kustomize-apply infrastructure/kubernetes/alerts

alerts-down: ensure-kind-context ## Delete sample Prometheus alert rules.
	$(MAKE) kustomize-delete infrastructure/kubernetes/alerts

grafana-port-forward: ensure-kind-context ## Port-forward local Grafana to localhost:$(GRAFANA_PORT).
	./scripts/port-forward-grafana.sh

prometheus-port-forward: ensure-kind-context ## Port-forward Prometheus to localhost:$(PROMETHEUS_PORT).
	$(KUBECTL) -n monitoring port-forward svc/kube-prometheus-stack-prometheus "$(PROMETHEUS_PORT):9090"

alertmanager-port-forward: ensure-kind-context ## Port-forward Alertmanager to localhost:$(ALERTMANAGER_PORT).
	$(KUBECTL) -n monitoring port-forward svc/kube-prometheus-stack-alertmanager "$(ALERTMANAGER_PORT):9093"

status: ensure-kind-context ## Show core lab resources.
	$(KUBECTL) get nodes
	$(KUBECTL) -n monitoring get pods
	$(KUBECTL) -n "$(APP_NAMESPACE)" get pods,svc,servicemonitor

clean: ## Delete the local lab cluster.
	$(MAKE) kind-down

kustomize-apply: ensure-kind-context ## Apply kustomization path passed as second make argument.
	@if [ -z "$(KUSTOMIZE_TARGET_PATH)" ]; then \
		echo "Usage: make kustomize-apply <kustomization-path>"; \
		exit 1; \
	fi
	@if [ ! -d "$(KUSTOMIZE_TARGET_PATH)" ]; then \
		echo "Error: directory not found: $(KUSTOMIZE_TARGET_PATH)"; \
		exit 1; \
	fi
	@if [ ! -f "$(KUSTOMIZE_TARGET_PATH)/kustomization.yaml" ]; then \
		echo "Error: kustomization.yaml not found in: $(KUSTOMIZE_TARGET_PATH)"; \
		exit 1; \
	fi
	kubectl kustomize --load-restrictor=LoadRestrictionsNone "$(KUSTOMIZE_TARGET_PATH)" | $(KUBECTL) apply -f -

kustomize-delete: ensure-kind-context ## Delete kustomization path passed as second make argument.
	@if [ -z "$(KUSTOMIZE_TARGET_PATH)" ]; then \
		echo "Usage: make kustomize-delete <kustomization-path>"; \
		exit 1; \
	fi
	@if [ ! -d "$(KUSTOMIZE_TARGET_PATH)" ]; then \
		echo "Error: directory not found: $(KUSTOMIZE_TARGET_PATH)"; \
		exit 1; \
	fi
	@if [ ! -f "$(KUSTOMIZE_TARGET_PATH)/kustomization.yaml" ]; then \
		echo "Error: kustomization.yaml not found in: $(KUSTOMIZE_TARGET_PATH)"; \
		exit 1; \
	fi
	kubectl kustomize --load-restrictor=LoadRestrictionsNone "$(KUSTOMIZE_TARGET_PATH)" | $(KUBECTL) delete --ignore-not-found=true -f -
