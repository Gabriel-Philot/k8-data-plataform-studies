# Prerequisites

This document outlines all requirements before deploying the K8s Data Platform.

## Required Tools

### Container & Orchestration

| Tool | Version | Purpose | Installation |
|------|---------|---------|--------------|
| Docker | 20.10+ | Container runtime | [docs.docker.com](https://docs.docker.com/get-docker/) |
| kubectl | 1.28+ | Kubernetes CLI | [kubernetes.io](https://kubernetes.io/docs/tasks/tools/) |
| Helm | 3.12+ | Kubernetes package manager | [helm.sh](https://helm.sh/docs/intro/install/) |

### Environment-Specific

**For Minikube (Local):**
| Tool | Version | Purpose |
|------|---------|---------|
| Minikube | 1.32+ | Local Kubernetes cluster |

**For EKS (AWS):**
| Tool | Version | Purpose |
|------|---------|---------|
| AWS CLI | 2.x | AWS resource management |
| Terraform | 1.3+ | Infrastructure as Code |

### GitOps & CI/CD

| Tool | Version | Purpose |
|------|---------|---------|
| ArgoCD CLI | 2.9+ | GitOps deployment management |
| Git | 2.x | Version control |

## System Requirements

### Minikube Environment

```
CPU:    2 cores (minimum)
Memory: 8 GB (minimum, 16 GB recommended)
Disk:   20 GB free space
```

### EKS Environment

Recommended node configuration:
```
Instance Type: t2.large (or equivalent)
Nodes:         2 (minimum)
```

## Account Requirements

### GitHub
- GitHub account with SSH key configured
- Repository fork or clone access

### AWS (EKS only)
- AWS account with appropriate permissions
- IAM user with programmatic access
- Required policies: EKS, EC2, VPC, IAM

## SSH Key Setup

The platform uses SSH keys for Git synchronization (Airflow DAGs, ArgoCD).

### Generate SSH Key

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

### Add to GitHub

1. Copy public key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
2. Go to GitHub → Settings → SSH and GPG keys → New SSH key
3. Paste the public key and save

### Verify Connection

```bash
ssh -T git@github.com
```

Expected output: `Hi <username>! You've successfully authenticated...`

## Environment Variables

Create a `.env` file or export these variables:

### AWS (EKS only)

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-2"
```

## Pre-flight Checklist

Before proceeding to deployment, verify:

- [ ] Docker is running: `docker info`
- [ ] kubectl is installed: `kubectl version --client`
- [ ] Helm is installed: `helm version`
- [ ] SSH key is configured and added to GitHub
- [ ] (Minikube) Minikube is installed: `minikube version`
- [ ] (EKS) AWS CLI is configured: `aws sts get-caller-identity`
- [ ] (EKS) Terraform is installed: `terraform version`

## Next Steps

Once prerequisites are met:
- **Local development**: Continue to [Minikube Deployment](03-minikube-deployment.md)
- **AWS production**: Continue to [EKS Deployment](04-eks-deployment.md)
