# AI Usage Disclosure (AI_USE.md)

**Student Name:** Dixant Soni  
**Roll Number:** 230103029  
**Course:** Cloud Computing (CS3081) Mini Project  
**Repository:** [https://github.com/DIXANTOFFICIAL1/Knowledge-Distillation-and-Deployment-of-a-Lightweight-](https://github.com/DIXANTOFFICIAL1/Knowledge-Distillation-and-Deployment-of-a-Lightweight-)

---

## 1. AI Tools Utilized

In accordance with course academic integrity guidelines, this document provides full disclosure regarding the generative AI tools employed during the project lifecycle.

| AI Tool | Version / Model | Primary Purpose | Scope of Usage |
|---|---|---|---|
| **Ollama / Phi-3.5** | `phi3.5-mini-instruct` (3.8B) | Teacher Model in Distillation Pipeline | Generated pseudo-labels for 3,000 commands in `commands_pool.jsonl`. Ran with fixed parameters (`temperature=0.0`, `seed=42`). |
| **Antigravity / Gemini** | Gemini 3.8 Flash | Code architecture, debugging, manifest design, and report typesetting assistance | Assisted in drafting Kubernetes YAML configurations, structuring the VLSM subnet calculations, optimizing Docker layers, and formatting the technical report. |

---

## 2. Specific Tasks and Usage Breakdown

### A. Teacher Label Generation (Task 1)
- **Role:** Ollama serving `phi3.5-mini-instruct` acted as the core teacher model.
- **Workflow:** Executed locally via automated sharded worker pods (`worker/worker.py`), feeding raw command strings with a rigid prompt structure to produce sequence-level distillation targets.

### B. Kubernetes and Infrastructure Manifests (Tasks 3 & 4)
- **Role:** Assisted in structuring valid Kubernetes manifests (`k3d.yaml`, `seaweedfs.yaml`, `deployment.yaml`, `ingress.yaml`, and `hpa.yaml`).
- **Prompting Strategy:** Provided exact resource specifications (1 vCPU, 1 GiB limits, Traefik ingress paths, probe intervals) and received scaffolded manifests adhering to Kubernetes v1.28 API specs.

### C. Networking Calculations and Stateless NACL Verification (Task 5)
- **Role:** Used to verify VLSM bit boundaries and cross-check stateless NACL packet simulation edge cases (e.g., ephemeral port return traffic rules).

---

## 3. Human Verification and Quality Control Protocols

No AI-generated output was accepted without rigorous empirical validation:
1. **Model Evaluation Quality Gate:** Every distilled student output was independently validated against `data/schema.json` using `tools/score.py` on `data/validation.jsonl`, enforcing $\ge 95\%$ JSON validity and strict substring extraction checks.
2. **NACL Simulation Verification:** All NACL rules in `network/nacl.json` were passed through `tools/nacl_sim.py --check` against test packet vectors, ensuring 100% compliance with deny-first ordering.
3. **Secret Scanning:** Scanned all codebases using `gitleaks` to confirm zero credential leakage.
4. **Reproducibility Testing:** Every make target (`make up`, `make down`, `make train SUBSET=50`) was tested locally in clean environments to ensure autonomous execution.
