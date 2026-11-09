# Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud

**Student Name:** Dixant Soni  
**Roll Number:** 230103029  
**GitHub Repository:** [https://github.com/DIXANTOFFICIAL1/Knowledge-Distillation-and-Deployment-of-a-Lightweight-](https://github.com/DIXANTOFFICIAL1/Knowledge-Distillation-and-Deployment-of-a-Lightweight-)  
**Git Tag:** `final`

---

## Project Overview

This repository implements an end-to-end cloud-native pipeline for **Sequence-Level Knowledge Distillation** and production deployment of a lightweight command-parsing language model (`EleutherAI/pythia-70m`) distilled from a 3.8B teacher model (`phi3.5-mini-instruct` via Ollama).

The system is deployed on a local Kubernetes cluster (`k3d`) backed by S3-compatible object storage (**SeaweedFS**), featuring automated Horizontal Pod Autoscaling (HPA), zero-downtime rolling updates, self-healing pod recovery, custom stateless Network Access Control Lists (NACLs), and an automated CI/CD pipeline with strict quality gates.

---

## Directory Structure

```text
.
├── 230103029.pdf                # 3-Page Handwritten Reflection Notes (Scanned)
├── report/
│   └── report.pdf               # Comprehensive 8-Page Technical Mini-Project Report
├── README.md                    # System architecture & deployment instructions
├── AI_USE.md                    # Disclosure of AI tools utilized and verification
├── Makefile                     # make up, make down, make train, make train SUBSET=50
├── cluster/
│   └── k3d.yaml                 # k3d cluster specification with Ingress port mappings
├── prompts/
│   └── teacher_prompt.txt       # Prompt used for phi3.5 pseudo-label generation
├── worker/
│   ├── worker.py                # Sharded Ollama teacher labeling worker
│   └── clean.py                 # Multi-stage cleaning and SHA-256 verification
├── training/
│   ├── config.yaml              # Hyperparameters, seed, and pinned library versions
│   ├── train.py                 # PyTorch & Transformers CPU fine-tuning script
│   └── loss.csv                 # Epoch-by-epoch loss log
├── service/
│   ├── app.py                   # FastAPI microservice (/parse, /healthz, /readyz)
│   ├── Dockerfile               # Optimized < 2 GB CPU-only PyTorch container
│   └── requirements.txt         # Pinned microservice dependencies
├── k8s/
│   ├── seaweedfs.yaml           # SeaweedFS master, volume, and S3 gateway
│   ├── secret.yaml              # S3 credentials Secret (namespaces data & app)
│   ├── deployment.yaml          # Inference service deployment with probes & limits
│   ├── service.yaml             # ClusterIP service exposing port 8000
│   ├── ingress.yaml             # Traefik Ingress routing /parse to app service
│   └── hpa.yaml                 # HorizontalPodAutoscaler (1-2 replicas, 70% CPU)
├── network/
│   ├── subnets.md               # VLSM subnet design for 10.20.0.0/16 & NACL rationale
│   ├── nacl.json                # Stateless NACL rules for public subnet
│   └── packets_sample.jsonl     # Validation packets for NACL simulation
├── data/
│   ├── commands_pool.jsonl      # 3,000 raw natural language voice commands
│   ├── validation.jsonl         # 100 labeled evaluation commands (never trained on)
│   ├── schema.json              # Strict 4-key JSON schema & 8 valid intents
│   └── rate_card.json           # Hypothetical cloud pricing card
├── datasets/
│   └── v1/
│       ├── train.jsonl          # Cleaned training dataset (first 1,500 records)
│       └── train.sha256         # SHA-256 checksum of train.jsonl
├── models/
│   └── v1/
│       └── model.sha256         # SHA-256 checksum of model weights
├── results/                     # All empirical logs, Locust outputs, & evaluations
│   ├── loadtest_stats.csv       # Locust load test statistics
│   ├── loadtest_failures.csv    # Locust failure log (0 failures)
│   ├── loadtest_headers.json    # Replica and version distribution headers
│   ├── teacher_validation.json  # phi3.5 benchmark report (82% full-frame)
│   ├── student_validation.json  # Distilled pythia-70m benchmark (70% full-frame)
│   ├── untrained_validation.json# Untrained baseline report (0% validity)
│   ├── cold_start_logs.txt      # Pod cold-start timings across 3 runs (median: 4.55s)
│   ├── recovery_logs.txt        # Pod termination self-healing log (< 2% error rate)
│   ├── rolling_update_logs.txt  # Rolling update v1 -> v2 and rollback log (< 0.5% errors)
│   ├── hpa_scaling_logs.txt     # HPA scale-up and scale-down event history
│   └── docker_stats_peak_memory.txt # 50-request benchmark at 1 CPU/1GiB (peak: 486 MiB)
├── tests/
│   └── test_service.py          # Unit test suite (schema, endpoints, fault injection)
└── .github/
    └── workflows/
        └── ci.yml               # CI/CD pipeline (lint, test, eval, quality gate, gitleaks)
```

---

## Prerequisites

- **Docker** $\ge 24.0$
- **k3d** $\ge 5.6.0$ & **kubectl** $\ge 1.28.0$
- **Python** 3.10+
- **Locust** (`pip install locust`)
- **Ollama** with `phi3.5:latest` (`ollama run phi3.5`)

---

## Quickstart Guide

### 1. Build and Deploy Local Cloud Cluster (`make up`)
To build the container image and deploy the entire stack from scratch in $\le 3$ commands:
```bash
make up
```
This command:
1. Provisions the local `k3d` cluster (`cluster/k3d.yaml`) with Traefik ingress mapped to host port `8080`.
2. Builds the lightweight inference container (`service/Dockerfile`, $< 2$ GB) and imports it into the cluster.
3. Applies SeaweedFS object storage, Secrets, Deployments, Services, Ingress, and HPA.

### 2. Verify Deployment
Check pod status:
```bash
kubectl get pods -n app
kubectl get ingress -n app
```
Test the inference endpoint via Ingress:
```bash
curl -X POST http://localhost:8080/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "set an alarm for seven thirty am tomorrow"}'
```
Expected Output:
```json
{"intent": "alarm_set", "date": "tomorrow", "time": "seven thirty am", "place": null}
```

### 3. Verify Health and Readiness Probes
```bash
curl -i http://localhost:8080/healthz   # Returns HTTP 200 {"status": "alive"}
curl -i http://localhost:8080/readyz    # Returns HTTP 200 {"status": "ready"}
```

---

## Model Training & Distillation (`make train`)

Fine-tune `EleutherAI/pythia-70m` on CPU using sequence-level distillation targets:
```bash
# Verify that training runs on a 50-sample subset:
make train SUBSET=50

# Run full fine-tuning (1,500 samples, 3 epochs):
make train
```

---

## Testing & Validation

### Run Unit Tests & NACL Check:
```bash
make test
```

### Run Model Evaluation:
```bash
python tools/score.py results/predictions_student.jsonl data/validation.jsonl --min-validity 95
```

### Run Locust Load Test:
```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
```

---

## Teardown (`make down`)

To cleanly delete the k3d cluster and free all local resources:
```bash
make down
```
