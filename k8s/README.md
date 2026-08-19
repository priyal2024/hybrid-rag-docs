# Kubernetes manifests

Plain manifests (no Helm/Kustomize — deliberately, at this project's size a
templating layer would add indirection without buying anything real).

## Local deploy (kind)

Docker Desktop wasn't available in this dev environment, so this was built
and verified against a local [`kind`](https://kind.sigs.k8s.io/) cluster
running on [Podman](https://podman.io/) instead of Docker — functionally
equivalent for everything here (a real container runtime, a real
containerd-backed Kubernetes node), just a different local backend.

```bash
# one-time: point the Docker CLI/kind at podman's machine socket
podman machine init && podman machine start
export DOCKER_HOST="unix://$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}')"
export KIND_EXPERIMENTAL_PROVIDER=podman

kind create cluster --name hybrid-rag-docs

# build images and load them into the kind node (no registry needed locally)
podman build -t hybrid-rag-docs-backend:local ./backend
podman build -t hybrid-rag-docs-frontend:local ./frontend
podman save hybrid-rag-docs-backend:local -o /tmp/backend.tar
podman save hybrid-rag-docs-frontend:local -o /tmp/frontend.tar
kind load image-archive /tmp/backend.tar --name hybrid-rag-docs
kind load image-archive /tmp/frontend.tar --name hybrid-rag-docs

# secrets — copy the template and fill in real values (never commit secret.yaml)
cp k8s/secret.example.yaml k8s/secret.yaml
# edit k8s/secret.yaml...

kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml -f k8s/secret.yaml
kubectl apply -f k8s/postgres.yaml -f k8s/redis.yaml -f k8s/kafka.yaml
kubectl wait --for=condition=Ready pod -l app=postgres -n hybrid-rag-docs --timeout=120s
kubectl apply -f k8s/migrate-job.yaml
kubectl wait --for=condition=Complete job/migrate -n hybrid-rag-docs --timeout=60s
kubectl apply -f k8s/backend.yaml -f k8s/worker.yaml -f k8s/frontend.yaml

# no ingress controller on a bare kind cluster — port-forward instead
kubectl port-forward -n hybrid-rag-docs svc/backend 8000:8000 &
kubectl port-forward -n hybrid-rag-docs svc/frontend 3000:3000 &
```

## On a real cluster (EKS, etc.)

- Swap the `image:` fields for a real registry reference (ECR) built by CI,
  and `imagePullPolicy: IfNotPresent` stays as-is once that's real.
- Apply `k8s/ingress.yaml` once an ingress controller (e.g. ingress-nginx) is
  installed — note the `proxy-buffering: off` annotation, which matters for
  `/ask`'s streamed SSE response.
- Swap the Postgres/Kafka StatefulSets for managed equivalents (RDS+pgvector,
  MSK) if running for real rather than as a demo — the app only cares about
  `DATABASE_URL` / `KAFKA_BOOTSTRAP_SERVERS`, so this is a config change, not
  a code change.

## What's here

| File | What |
|---|---|
| `namespace.yaml` | `hybrid-rag-docs` namespace |
| `configmap.yaml` | non-secret config (Redis URL, LLM base URL/model, CORS origins) |
| `secret.example.yaml` | template for DB credentials, LLM key, auth secrets — copy to `secret.yaml` (gitignored) |
| `postgres.yaml` | StatefulSet + PVC (pgvector image) + Service |
| `redis.yaml` | Deployment + Service |
| `kafka.yaml` | StatefulSet (KRaft mode, single node) + Service |
| `migrate-job.yaml` | one-shot Job running `alembic upgrade head` |
| `backend.yaml` | FastAPI Deployment (2 replicas) + Service, `/health` probes |
| `worker.yaml` | ingestion worker Deployment (Kafka consumer) |
| `frontend.yaml` | Next.js Deployment (2 replicas) + Service |
| `ingress.yaml` | routes `/` → frontend, `/api-backend` → backend (needs an ingress controller) |
