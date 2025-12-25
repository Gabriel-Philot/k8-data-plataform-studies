# Minikube Deployment

This guide covers deploying the K8s Data Platform on Minikube for local development and testing.

## Overview

Estimated time: 15-20 minutes

**What you'll deploy:**
- ArgoCD (GitOps)
- PostgreSQL (Airflow metadata)
- MinIO (Object storage)
- Apache Spark Operator
- Apache Airflow
- JupyterLab (optional)
- Prometheus & Grafana (optional)

## Step 1: Start Minikube

Start Minikube with adequate resources:

```bash
minikube start --memory=8000 --cpus=2
```

Enable LoadBalancer access (run in a separate terminal, keep it running):

```bash
minikube tunnel
```

> **Note**: The tunnel command may require sudo privileges.

## Step 2: Create Namespaces

```bash
kubectl create namespace orchestrator
kubectl create namespace database
kubectl create namespace ingestion
kubectl create namespace processing
kubectl create namespace datastore
kubectl create namespace deepstorage
kubectl create namespace cicd
kubectl create namespace app
kubectl create namespace management
kubectl create namespace misc
kubectl create namespace monitoring
kubectl create namespace jupyter
```

## Step 3: Install ArgoCD

Add Helm repository and install ArgoCD:

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd argo/argo-cd --namespace cicd --version 5.27.1
```

Expose ArgoCD via LoadBalancer:

```bash
kubectl patch svc argocd-server -n cicd -p '{"spec": {"type": "LoadBalancer"}}'
```

Install ArgoCD CLI:

```bash
sudo curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo chmod +x /usr/local/bin/argocd
```

## Step 4: Configure ArgoCD

Get ArgoCD server IP and login:

```bash
# Get LoadBalancer IP
ARGOCD_LB=$(kubectl get services -n cicd \
  -l app.kubernetes.io/name=argocd-server,app.kubernetes.io/instance=argocd \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].ip}")

# Login to ArgoCD
kubectl get secret argocd-initial-admin-secret -n cicd \
  -o jsonpath="{.data.password}" | base64 -d | \
  xargs -t -I {} argocd login $ARGOCD_LB --username admin --password {} --insecure
```

Add your GitHub repository:

```bash
# Replace with your repository and SSH key path
argocd repo add git@github.com:YOUR-USERNAME/k8-data-plataform-studies.git \
  --ssh-private-key-path ~/.ssh/id_ed25519 \
  --insecure-skip-server-verification
```

Access ArgoCD UI:

```bash
echo "ArgoCD URL: http://$ARGOCD_LB"
echo "Username: admin"
echo "Password: $(kubectl get secret argocd-initial-admin-secret -n cicd -o jsonpath='{.data.password}' | base64 -d)"
```

## Step 5: Deploy Core Infrastructure

### Reflector (Secret Management)

```bash
kubectl apply -f minikube/manifests/management/reflector.yaml
```

Wait for Reflector to be ready before continuing (~1 minute).

### Secrets

> **Important**: Update `minikube/manifests/misc/secrets.yaml` with your repository URL before applying.

```bash
kubectl apply -f minikube/manifests/misc/secrets.yaml
```

### Databases and Storage

```bash
# PostgreSQL for Airflow metadata
kubectl apply -f minikube/manifests/database/postgres.yaml

# MinIO for object storage
kubectl apply -f minikube/manifests/deepstorage/minio.yaml
```

Wait for both to be healthy in ArgoCD before continuing (~3-5 minutes).

## Step 6: Deploy Processing Components

Add required Helm repositories:

```bash
helm repo add spark-operator https://kubeflow.github.io/spark-operator
helm repo add apache-airflow https://airflow.apache.org/
helm repo update
```

Deploy Spark Operator:

```bash
kubectl apply -f minikube/manifests/processing/spark.yaml
```

## Step 7: Deploy Airflow

Create SSH secret for Git synchronization:

```bash
kubectl create secret generic airflow-ssh-secret \
  --from-file=gitSshKey=$HOME/.ssh/id_ed25519 \
  -n orchestrator
```

> **Important**: Update the repository URL in `minikube/manifests/orchestrator/airflow.yaml` before applying.

Deploy Airflow:

```bash
kubectl apply -f minikube/manifests/orchestrator/airflow.yaml
```

Deploy access controls:

> **Important**: Update the repository URL in `minikube/manifests/misc/access-control.yaml` first.

```bash
kubectl apply -f minikube/manifests/misc/access-control.yaml
```

Import Airflow connections:

```bash
kubectl get pods --no-headers -o custom-columns=":metadata.name" -n orchestrator | \
  grep scheduler | \
  xargs -i sh -c 'kubectl cp images/airflow/connections.json orchestrator/{}:./ -c scheduler && \
  kubectl -n orchestrator exec {} -- airflow connections import connections.json'
```

## Step 8: Build Docker Images

Build images using Minikube's Docker daemon:

```bash
# Set Docker environment to Minikube
eval $(minikube docker-env)

# Build ingestion image
docker build --no-cache \
  -f images/python_ingestion/dockerfile \
  images/python_ingestion/ \
  -t gabrielphilot/brewapi-ingestion-minio:0.1

# Build Spark processing image
docker build --no-cache \
  -f images/spark_brewery/dockerfile \
  images/spark_brewery/ \
  -t gabrielphilot/brew-process-spark-delta:0.2
```

## Step 9: Verify Deployment

### Access Airflow UI

```bash
AIRFLOW_IP=$(kubectl get services -n orchestrator \
  -l component=webserver,argocd.argoproj.io/instance=airflow \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].ip}")

echo "Airflow URL: http://${AIRFLOW_IP}:8080"
echo "Username: admin"
echo "Password: admin"
```

### Access MinIO Console

```bash
MINIO_IP=$(kubectl get services -n deepstorage \
  -l app.kubernetes.io/name=minio \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].ip}")

echo "MinIO URL: http://${MINIO_IP}:9000"
echo "Access Key: $(kubectl get secret minio-secrets -n deepstorage -o jsonpath='{.data.root-user}' | base64 -d)"
echo "Secret Key: $(kubectl get secret minio-secrets -n deepstorage -o jsonpath='{.data.root-password}' | base64 -d)"
```

## Optional: Deploy JupyterLab

Build and deploy JupyterLab for data exploration:

```bash
# Build image
eval $(minikube docker-env)
docker build --no-cache \
  -f images/custom_jupyterlab/dockerfile \
  images/custom_jupyterlab/ \
  -t gabrielphilot/custom_jupyterlab:0.1

# Deploy
kubectl apply -f minikube/manifests/notebook/jup-notebook.yaml
```

Access JupyterLab:

```bash
# Get external IP
kubectl get svc -n jupyter custom-jupyter

# Get authentication token
kubectl exec -it $(kubectl get pods -n jupyter -l app=custom-jupyter -o jsonpath='{.items[0].metadata.name}') \
  -n jupyter -- jupyter server list
```

## Optional: Deploy Monitoring

```bash
kubectl apply -f minikube/manifests/monitoring/prometheus.yaml
kubectl apply -f minikube/manifests/monitoring/grafana.yaml
```

Access Grafana:

```bash
kubectl get services --namespace monitoring
# Grafana is on port 80
```

## Verification Checklist

Verify all components are running:

```bash
# Check ArgoCD applications
argocd app list

# Check pods in each namespace
kubectl get pods -n orchestrator
kubectl get pods -n processing
kubectl get pods -n deepstorage
kubectl get pods -n database
```

Expected status: All applications should show `Synced` and `Healthy` in ArgoCD.

## Cleanup

To tear down the environment:

```bash
# Delete Minikube cluster
minikube delete

# Or just stop it to resume later
minikube stop
```

## Next Steps

- [Operating the Platform](05-operating-the-platform.md) - Run data pipelines
- [Troubleshooting](06-troubleshooting.md) - Common issues and solutions
