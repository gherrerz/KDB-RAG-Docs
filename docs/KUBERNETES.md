# Kubernetes Deployment Guide

Esta guia agrega despliegue en Kubernetes sin reemplazar el flujo local con
Docker Compose.

## Objetivo de compatibilidad

- Docker Compose sigue siendo el camino local principal.
- Kubernetes se agrega como ruta de despliegue paralela.
- Se reutiliza el mismo contrato de runtime:
  - variables de entorno de `src/coderag/core/settings.py`
  - imagen construida desde `Dockerfile`
  - separacion `api` + `worker`

## Artefactos incluidos

Directorio `k8s/`:

- `k8s/base/namespace.yaml`
- `k8s/base/configmap-app.yaml`
- `k8s/base/secret-app.example.yaml`
- `k8s/base/networkpolicy.yaml`
- `k8s/base/pvc-data.yaml`
- `k8s/base/deployment-api.yaml`
- `k8s/base/service-api.yaml`
- `k8s/base/deployment-worker.yaml`
- `k8s/base/ingress-api.yaml` (TLS habilitado)
- `k8s/base/kustomization.yaml`
- `k8s/overlays/dev/kustomization.yaml`
- `k8s/overlays/prod/kustomization.yaml`

## Prerequisitos

- Kubernetes cluster (minikube, kind, AKS, EKS, GKE)
- kubectl
- kustomize (integrado en kubectl moderno)
- Imagen publicada accesible por el cluster
- Secret real creado desde template

## Build y push de imagen

Ejemplo:

```powershell
docker build -t ghcr.io/gherrerz/kdb-rag-docs:latest .
docker push ghcr.io/gherrerz/kdb-rag-docs:latest
```

Ajusta el tag y registro segun tu entorno.

Los overlays usan un nombre base neutral (`kdb-rag-docs`) y luego mapean
`newName/newTag`:

- dev: `k8s/overlays/dev/kustomization.yaml`
- prod: `k8s/overlays/prod/kustomization.yaml`

Actualiza esos valores antes de desplegar.

En el overlay `dev` se usa `imagePullPolicy: Never` para facilitar pruebas con
imagen local (`docker build -t kdb-rag-docs:latest .`).

## Configuracion de secretos

1. Copia `k8s/base/secret-app.example.yaml` a un archivo local no versionado.
2. Completa credenciales reales (en especial `NEO4J_PASSWORD`, no usar
  placeholders como `REPLACE_ME`).
3. Aplica el secreto antes del deploy:

```powershell
kubectl apply -f k8s/base/secret-app.example.yaml
```

Recomendacion: en produccion, usar External Secrets o Sealed Secrets.

Evita importar todo `.env` como Secret porque puede sobrescribir variables de
ConfigMap (por ejemplo `REDIS_URL`, `USE_RQ`, etc.).

Alternativa segura para secreto real (solo llaves sensibles):

```powershell
kubectl create secret generic coderag-app-secrets --namespace coderag \
  --from-literal=OPENAI_API_KEY="<openai-key>" \
  --from-literal=GEMINI_API_KEY="<gemini-key>" \
  --from-literal=VERTEX_AI_API_KEY="<vertex-key>" \
  --from-literal=VERTEX_PROJECT_ID="<vertex-project>" \
  --from-literal=NEO4J_PASSWORD="<neo4j-password>" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Deploy en entorno dev

```powershell
kubectl apply -k k8s/overlays/dev
```

El overlay `dev` incluye dependencias in-cluster:

- Redis (Service `redis`)
- Neo4j (Service `neo4j`)

El baseline `base` aplica tambien:

- NetworkPolicy para limitar trafico entre `api`/`worker` y `redis`/`neo4j`.
- Ingress con redireccion HTTPS y `tls.secretName=coderag-api-tls`.

Si no usas cert-manager, crea el secret TLS manualmente:

```powershell
kubectl create secret tls coderag-api-tls --namespace coderag \
  --cert=<ruta-cert.pem> --key=<ruta-key.pem>
```

Verifica estado:

```powershell
kubectl get pods -n coderag
kubectl get svc -n coderag
```

## Probes y endpoints

- Liveness probe: `GET /health`
- Readiness probe: `GET /readiness`
- Worker: startup/readiness/liveness probe via ping a Redis URL activa.
- Overlay `dev`: Redis y Neo4j incluyen probes y recursos base para mejorar
  estabilidad operativa.

Si haces port-forward:

```powershell
kubectl port-forward -n coderag svc/coderag-api 8000:8000
```

Luego:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/readiness`
- `http://127.0.0.1:8000/docs`

## Persistencia

- Se monta PVC `coderag-data-pvc` en `/data`.
- `DATA_DIR=/data` y `CHROMA_PERSIST_DIR=/data/chromadb`.

## Notas operativas

- `USE_RQ=true` requiere Redis alcanzable desde el cluster.
- En produccion se recomienda usar Redis/Neo4j gestionados (externos).
- Si no usaras async, puedes desactivar worker y `USE_RQ=false`.

## Rollback rapido

```powershell
kubectl rollout undo deployment/coderag-api -n coderag
kubectl rollout undo deployment/coderag-worker -n coderag
```

## Validacion funcional minima

1. API lista (`/readiness` devuelve 200).
2. Ingesta sync funciona (`POST /sources/ingest`).
3. Ingesta async funciona (`POST /sources/ingest/async`) con worker activo.
4. Query funciona (`POST /query`) con `citations`.
