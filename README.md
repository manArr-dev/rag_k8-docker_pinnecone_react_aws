# Document Chat (RAG)

Chat with your own documents. Upload PDFs or text files; answers are generated
from the passages retrieved for each question and cite them.

```
Browser ── React chat UI (nginx) ──/api──▶ FastAPI
                                             ├─ PyTorch bi-encoder  → query / chunk embeddings
                                             ├─ Pinecone            → vector search (top 20)
                                             ├─ PyTorch cross-encoder → rerank (top 5)
                                             └─ Claude              → streamed, cited answer
```

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI service. PyTorch models in `app/rag/embeddings.py` and `reranker.py`, Pinecone in `vectorstore.py`, generation in `generator.py`. |
| `frontend/` | React + TypeScript chat UI (Vite), served by nginx, which also proxies `/api`. |
| `k8s/` | Kustomize manifests: deployments, services, HPA, PDBs, ALB ingress. |
| `infra/terraform/` | VPC, EKS, ECR, AWS Load Balancer Controller, GitHub Actions deploy role. |
| `.github/workflows/` | `ci.yml` (tests, builds, validation) and `deploy.yml` (ECR push + EKS rollout). |

## Run locally

You need Docker, an [Anthropic API key](https://console.anthropic.com/) and a
[Pinecone API key](https://app.pinecone.io/).

```bash
cp .env.example .env      # fill in ANTHROPIC_API_KEY, PINECONE_API_KEY, ADMIN_API_KEY
docker compose up --build
```

Open http://localhost:8080, click **Add documents**, paste your `ADMIN_API_KEY`
and upload a file. The Pinecone index (`rag-documents`, serverless, 384
dimensions) is created on first start.

The first build downloads PyTorch and the two models (about 1.5 GB in total).

### Without Docker

```bash
# API on :8000
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example .env                               # fill in the keys; set APP_ENV=development
uvicorn app.main:create_app --factory --reload

# UI on :5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend && ruff check . && pytest
cd frontend && npm test && npm run build
```

The backend tests swap the models, Pinecone and Claude for in-memory fakes, so
they need no keys and run in under a second.

## API

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/chat` | Body `{"message": "...", "history": [{"role": "user", "content": "..."}]}`. Responds with server-sent events: `sources`, then `token` events, then `done` or `error`. |
| `POST` | `/api/documents` | Multipart `file` (`.pdf`, `.txt`, `.md`). Requires `X-API-Key`. Re-uploading a file with the same name replaces it. |
| `DELETE` | `/api/documents/{doc_id}` | Requires `X-API-Key`. `doc_id` is returned by the upload. |
| `GET` | `/healthz`, `/readyz` | Liveness and readiness. |

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" -F file=@handbook.pdf http://localhost:8080/api/documents
curl -N -H "Content-Type: application/json" -d '{"message": "What is the leave policy?"}' \
  http://localhost:8080/api/chat
```

## Configuration

All settings are environment variables; `backend/app/config.py` is the full
list and `.env.example` shows the common ones.

- **Model.** `LLM_MODEL` defaults to `claude-opus-5-5`; `LLM_EFFORT` (`low` to
  `max`, default `medium`) trades answer depth against latency and cost.
- **Changing the embedding model.** The Docker image bakes the models in and
  runs offline. To use different ones, set `EMBEDDING_MODEL` / `RERANKER_MODEL`
  *and* rebuild with the matching `--build-arg`. A model with a different
  vector size needs a new Pinecone index (`PINECONE_INDEX`) and a re-ingest;
  the API refuses to start against an index of the wrong dimension.
- **Uploads are closed by default.** Without `ADMIN_API_KEY`, the document
  endpoints return 403 unless `APP_ENV=development`.

## Deploy to AWS

One-time setup, then every push to `main` deploys.

**Prerequisites:** AWS CLI (authenticated as an admin), Terraform ≥ 1.9,
kubectl, and this project pushed to its own GitHub repository.

### 1. Create the infrastructure

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set github_repository = "owner/repo"
terraform init
terraform apply
```

This takes around 20 minutes and creates a VPC, an EKS cluster with two
`m6i.large` nodes, two ECR repositories, the AWS Load Balancer Controller, and
an IAM role that only GitHub Actions runs on your `main` branch can assume.
**It costs money while it exists**, roughly $250–300/month at the defaults
(EKS control plane, two nodes, NAT gateway, load balancer).

If `kubernetes_version` is rejected, set it to a version from
`aws eks describe-cluster-versions`.

### 2. Create the namespace and secrets

```bash
$(terraform output -raw configure_kubectl)
kubectl create namespace rag
kubectl -n rag create secret generic rag-secrets \
  --from-literal=ANTHROPIC_API_KEY=... \
  --from-literal=PINECONE_API_KEY=... \
  --from-literal=ADMIN_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

### 3. Point GitHub at AWS

In the repository, under **Settings → Secrets and variables → Actions →
Variables**, add:

| Variable | Value |
| --- | --- |
| `AWS_REGION` | `terraform output -raw aws_region` |
| `AWS_ROLE_ARN` | `terraform output -raw github_actions_role_arn` |
| `EKS_CLUSTER_NAME` | `terraform output -raw cluster_name` |

No AWS access keys are stored in GitHub; the workflow authenticates with OIDC.

### 4. Deploy

Push to `main` (or run the **Deploy** workflow manually). It runs CI, pushes
both images to ECR tagged with the commit SHA, applies `k8s/overlays/prod` and
waits for the rollout. Then:

```bash
kubectl -n rag get ingress rag     # ADDRESS is the public URL (allow a few minutes for the ALB)
```

To roll back: `kubectl -n rag rollout undo deployment/backend` (and
`deployment/frontend`), or re-run the Deploy workflow on an earlier commit.

### Before real users

- **HTTPS.** The ingress serves plain HTTP until you add a certificate. Request
  one in ACM and uncomment the patch in `k8s/overlays/prod/kustomization.yaml`.
- **Chat is unauthenticated.** Anyone who can reach the URL can ask questions
  and spend your Anthropic budget. Put it behind your identity provider (ALB
  OIDC/Cognito authentication) or restrict the ALB with
  `alb.ingress.kubernetes.io/inbound-cidrs`, and attach AWS WAF rate limiting.
- **Secrets.** The `rag-secrets` Secret is created by hand above. For rotation
  and audit, move to AWS Secrets Manager with the External Secrets Operator.
- **Terraform state** is local unless you enable the S3 backend in
  `infra/terraform/versions.tf`.
- **Dependencies** in `backend/requirements.txt` are version ranges. Pin them
  (for example with `pip-compile`) for reproducible builds.

### Tear down

```bash
kubectl delete -k k8s/overlays/prod    # removes the ALB first, so the VPC can be deleted
cd infra/terraform && terraform destroy
```

## How it behaves

- **Ingestion** splits each page into ~1,200-character chunks with 200
  characters of overlap, embeds them with `BAAI/bge-small-en-v1.5`, and upserts
  them to Pinecone with the text and source in metadata.
- **Retrieval** embeds the question (plus the previous user turn, so follow-ups
  like "and how much is that?" still find the right passages), takes the 20
  nearest chunks, and reranks them with a cross-encoder down to 5.
- **Generation** sends those passages and the conversation to Claude and
  streams the answer. The system prompt tells the model to answer only from the
  passages, cite them as `[1]`, `[2]`, and treat document text as data rather
  than instructions.
- **Scaling.** Each backend pod holds the models in memory (~1 GB) and runs one
  worker; the HPA adds pods at 70% CPU, between 2 and 6.
