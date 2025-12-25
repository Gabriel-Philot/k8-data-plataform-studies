# EKS Deployment

This guide covers deploying the K8s Data Platform on Amazon EKS for production workloads.

## Overview

Estimated time: 30-45 minutes

**What you'll deploy:**
- EKS Cluster via Terraform
- ArgoCD (GitOps)
- PostgreSQL (Airflow metadata)
- MinIO (Object storage)
- Apache Spark Operator
- Apache Airflow
- JupyterLab (optional)

## Step 1: Configure AWS Credentials

Ensure AWS CLI is configured:

```bash
aws configure
# Or use environment variables:
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-2"
```

Verify access:

```bash
aws sts get-caller-identity
```

## Step 2: Provision EKS Cluster

Navigate to Terraform directory:

```bash
cd eks/infra-terraform
```

Create `terraform.tfvars` with your credentials:

```hcl
aws_profile     = "your-aws-profile"
var_access_key  = "your-access-key"
var_secret_key  = "your-secret-key"
cluster_name    = "k8s-aws"
cluster_version = "1.30"
region          = "us-east-2"
```

Initialize and apply Terraform:

```bash
terraform init
terraform plan
terraform apply --auto-approve
```

> **Note**: This creates a VPC, subnets, and 2-node EKS cluster with t2.large spot instances. Takes ~15 minutes.

Connect kubectl to EKS:

```bash
aws eks --region us-east-2 update-kubeconfig --name k8s-aws
```

Verify connection:

```bash
kubectl get nodes
```

## Step 3: Create Namespaces

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

## Step 4: Install ArgoCD

Add Helm repository and install:

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argocd argo/argo-cd --namespace cicd --version 5.27.1
```

Expose via LoadBalancer:

```bash
kubectl patch svc argocd-server -n cicd -p '{"spec": {"type": "LoadBalancer"}}'
```

Install ArgoCD CLI:

```bash
sudo curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo chmod +x /usr/local/bin/argocd
```

## Step 5: Configure ArgoCD

Get LoadBalancer hostname and login:

```bash
# Get LoadBalancer hostname (AWS uses hostname, not IP)
ARGOCD_LB=$(kubectl get services -n cicd \
  -l app.kubernetes.io/name=argocd-server,app.kubernetes.io/instance=argocd \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].hostname}")

# Login
kubectl get secret argocd-initial-admin-secret -n cicd \
  -o jsonpath="{.data.password}" | base64 -d | \
  xargs -t -I {} argocd login $ARGOCD_LB --username admin --password {} --insecure
```

Add your GitHub repository:

```bash
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

## Step 6: Deploy Core Infrastructure

### Reflector

```bash
kubectl apply -f eks/manifests/management/reflector.yaml
```

Wait for Reflector to be ready (~1 minute).

### Secrets

> **Important**: Update repository URL in `eks/manifests/misc/secrets.yaml` before applying.

```bash
kubectl apply -f eks/manifests/misc/secrets.yaml
```

### Databases and Storage

> **Note**: EKS manifests use `storageClass: gp2` for AWS EBS volumes.

```bash
kubectl apply -f eks/manifests/database/postgres.yaml
kubectl apply -f eks/manifests/deepstorage/minio.yaml
```

Wait for both to be healthy in ArgoCD (~5 minutes).

## Step 7: Deploy Processing Components

Add Helm repositories:

```bash
helm repo add spark-operator https://kubeflow.github.io/spark-operator
helm repo add apache-airflow https://airflow.apache.org/
helm repo update
```

Deploy Spark Operator:

```bash
kubectl apply -f eks/manifests/processing/spark.yaml
```

## Step 8: Deploy Airflow

Create SSH secret:

```bash
kubectl create secret generic airflow-ssh-secret \
  --from-file=gitSshKey=$HOME/.ssh/id_ed25519 \
  -n orchestrator
```

> **Important**: Update repository URL in `eks/manifests/orchestrator/airflow.yaml`.

Deploy Airflow:

```bash
kubectl apply -f eks/manifests/orchestrator/airflow.yaml
```

Deploy access controls:

> **Important**: Update repository URL in `eks/manifests/misc/access-control.yaml`.

```bash
kubectl apply -f eks/manifests/misc/access-control.yaml
```

Import connections:

```bash
kubectl get pods --no-headers -o custom-columns=":metadata.name" -n orchestrator | \
  grep scheduler | \
  xargs -i sh -c 'kubectl cp images/airflow/connections.json orchestrator/{}:./ -c scheduler && \
  kubectl -n orchestrator exec {} -- airflow connections import connections.json'
```

## Step 9: Build and Push Docker Images

For EKS, images must be pushed to a container registry:

```bash
# Login to DockerHub (or your registry)
docker login

# Build and push ingestion image
docker build --no-cache \
  -f images/python_ingestion/dockerfile \
  images/python_ingestion/ \
  -t gabrielphilot/brewapi-ingestion-minio:0.1
docker push gabrielphilot/brewapi-ingestion-minio:0.1

# Build and push Spark image
docker build --no-cache \
  -f images/spark_eks_brewery/dockerfile \
  images/spark_eks_brewery/ \
  -t gabrielphilot/brew-process-spark-delta-eks:0.2
docker push gabrielphilot/brew-process-spark-delta-eks:0.2
```

> **Note**: EKS uses a specific Spark image (`spark_eks_brewery`) optimized for AWS.

## Step 10: Verify Deployment

### Access Airflow

```bash
AIRFLOW_LB=$(kubectl get services -n orchestrator \
  -l component=webserver,argocd.argoproj.io/instance=airflow \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].hostname}")

echo "Airflow URL: http://${AIRFLOW_LB}:8080"
echo "Username: admin"
echo "Password: admin"
```

### Access MinIO

```bash
MINIO_LB=$(kubectl get services -n deepstorage \
  -l app.kubernetes.io/name=minio \
  -o jsonpath="{.items[0].status.loadBalancer.ingress[0].hostname}")

echo "MinIO URL: http://${MINIO_LB}:9000"
echo "Access Key: $(kubectl get secret minio-secrets -n deepstorage -o jsonpath='{.data.root-user}' | base64 -d)"
echo "Secret Key: $(kubectl get secret minio-secrets -n deepstorage -o jsonpath='{.data.root-password}' | base64 -d)"
```

## Optional: Deploy JupyterLab

```bash
# Build and push image
docker build --no-cache \
  -f images/custom_jupyterlab/dockerfile \
  images/custom_jupyterlab/ \
  -t gabrielphilot/custom_jupyterlab:0.1
docker push gabrielphilot/custom_jupyterlab:0.1

# Deploy
kubectl apply -f eks/manifests/notebook/jup-notebook.yaml
```

Access JupyterLab:

```bash
JUPYTER_LB=$(kubectl get svc -n jupyter custom-jupyter \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "JupyterLab URL: http://${JUPYTER_LB}:8888"

# Get token
kubectl exec -it $(kubectl get pods -n jupyter -l app=custom-jupyter \
  -o jsonpath='{.items[0].metadata.name}') -n jupyter -- jupyter server list
```

## Cost Considerations

EKS incurs AWS charges for:
- EKS control plane: ~$0.10/hour
- EC2 instances (2x t2.large spot): Variable, ~$0.02-0.04/hour each
- EBS volumes: ~$0.10/GB/month
- LoadBalancers: ~$0.025/hour each

**Estimated monthly cost**: $100-200 for a minimal deployment

## Cleanup

**Delete all Kubernetes resources:**

```bash
# Delete ArgoCD applications
argocd app delete --all

# Or manually delete namespaces
kubectl delete namespace orchestrator database processing deepstorage cicd management misc monitoring jupyter
```

**Destroy EKS infrastructure:**

```bash
cd eks/infra-terraform
terraform destroy --auto-approve
```

> **Warning**: This permanently deletes all data in the cluster.

## Next Steps

- [Operating the Platform](05-operating-the-platform.md) - Run data pipelines
- [Troubleshooting](06-troubleshooting.md) - Common issues
