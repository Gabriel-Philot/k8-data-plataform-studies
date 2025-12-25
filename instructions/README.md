# Instructions Overview

This folder contains comprehensive documentation for deploying and operating the K8s Data Platform.

## Documentation Structure

| Document | Description |
|----------|-------------|
| [01-prerequisites.md](01-prerequisites.md) | Required tools, accounts, and environment setup |
| [02-architecture.md](02-architecture.md) | System architecture, components, and data flow |
| [03-minikube-deployment.md](03-minikube-deployment.md) | Local development deployment guide |
| [04-eks-deployment.md](04-eks-deployment.md) | AWS EKS production deployment guide |
| [05-operating-the-platform.md](05-operating-the-platform.md) | Day-to-day operations and data pipeline execution |
| [06-troubleshooting.md](06-troubleshooting.md) | Common issues and debugging strategies |

## Quick Navigation

**First time setup?** Start with [Prerequisites](01-prerequisites.md), then choose your deployment target:
- Local development → [Minikube Deployment](03-minikube-deployment.md)
- AWS cloud → [EKS Deployment](04-eks-deployment.md)

**Running pipelines?** See [Operating the Platform](05-operating-the-platform.md)

**Something broken?** Check [Troubleshooting](06-troubleshooting.md)

## Environment Comparison

| Aspect | Minikube | EKS |
|--------|----------|-----|
| Purpose | Development/Testing | Production |
| Storage Class | default | gp2 |
| Load Balancer | minikube tunnel | AWS ELB |
| Cost | Free | AWS charges apply |
| Setup Time | ~15 minutes | ~30 minutes |
| Recommended RAM | 8GB+ | Based on node type |
