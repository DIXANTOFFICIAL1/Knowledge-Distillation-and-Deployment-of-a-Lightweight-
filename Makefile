# Makefile for Cloud Computing Mini Project
# Supports: make up, make down, make train, make train SUBSET=50

.PHONY: up down train test clean

up:
	@echo "=== [1/3] Creating k3d cluster ==="
	k3d cluster create --config cluster/k3d.yaml || true
	@echo "=== [2/3] Building container image and importing to k3d ==="
	docker build -t parser-service:latest -f service/Dockerfile .
	k3d image import parser-service:latest -c cloud-mini-cluster
	@echo "=== [3/3] Deploying SeaweedFS and Kubernetes manifests ==="
	kubectl apply -f k8s/seaweedfs.yaml
	kubectl apply -f k8s/secret.yaml
	kubectl wait --for=condition=ready pod -l app=seaweedfs -n data --timeout=90s || true
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	kubectl apply -f k8s/ingress.yaml
	kubectl apply -f k8s/hpa.yaml
	@echo "Deployment complete. Endpoint accessible via http://localhost:8080/parse"

down:
	@echo "=== Deleting k3d cluster ==="
	k3d cluster delete cloud-mini-cluster

train:
	@echo "=== Starting Training (SUBSET=$(SUBSET)) ==="
	python training/train.py $(if $(SUBSET),--subset $(SUBSET),)

test:
	@echo "=== Running Unit Tests ==="
	pytest tests/ -v
	@echo "=== Checking NACL Rules ==="
	python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check

clean:
	rm -rf __pycache__ .pytest_cache training/checkpoints_*
