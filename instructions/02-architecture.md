# Architecture

This document describes the system architecture, components, and data flow of the K8s Data Platform.

## High-Level Overview

The platform implements a modern data lakehouse architecture on Kubernetes, featuring:

- **Medallion Architecture**: Bronze → Silver → Gold data layers
- **GitOps Deployment**: ArgoCD manages all Kubernetes resources
- **Event-Driven Pipelines**: Airflow Dataset triggers for pipeline orchestration
- **Cloud-Native Storage**: MinIO as S3-compatible object storage

## Component Architecture

### Kubernetes Namespaces

```
├── orchestrator     # Airflow (workflow orchestration)
├── processing       # Spark Operator (data processing)
├── database         # PostgreSQL (Airflow metadata)
├── deepstorage      # MinIO (S3-compatible lakehouse)
├── cicd             # ArgoCD (GitOps)
├── management       # Reflector (secret distribution)
├── monitoring       # Prometheus & Grafana
├── jupyter          # JupyterLab (data exploration)
└── misc             # Secrets & RBAC configurations
```

### Core Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestrator | Apache Airflow 2.x | DAG scheduling, workflow management |
| Processing Engine | Apache Spark 3.3.2 | Distributed data processing |
| Storage Layer | MinIO + Delta Lake | Object storage with ACID transactions |
| Metadata DB | PostgreSQL 12 | Airflow metadata persistence |
| GitOps | ArgoCD | Declarative Kubernetes deployments |
| Secret Management | Reflector | Cross-namespace secret synchronization |

## Data Flow Architecture

### Medallion Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAKEHOUSE                          │
├─────────────────┬─────────────────┬─────────────────────────────┤
│     BRONZE      │     SILVER      │           GOLD              │
├─────────────────┼─────────────────┼─────────────────────────────┤
│ Raw API Data    │ Cleaned Data    │ Aggregated Analytics        │
│ JSON format     │ Deduplicated    │ Business-ready views        │
│ Partitioned     │ Validated       │ Optimized for queries       │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

### Pipeline Stages

**DAG 1: Ingestion & Validation** (`brewapi-ingestion-validation-minio`)
1. Fetch data from Brewery API
2. Write raw data to Bronze layer (MinIO)
3. Validate record counts and data integrity
4. Trigger downstream processing via Airflow Dataset

**DAG 2: Processing & Transformation** (`brew-process-transformation`)
1. Triggered by Dataset update from DAG 1
2. Bronze → Silver: Cleansing, deduplication, schema enforcement
3. Silver → Gold: Aggregations, business logic, analytics tables

## Execution Model

### Airflow with KubernetesExecutor

Each task runs in an isolated Kubernetes pod:

```
┌──────────────────────────────────────────────────────────┐
│                    AIRFLOW SCHEDULER                      │
│                    (orchestrator ns)                      │
└────────────────────────┬─────────────────────────────────┘
                         │ spawns pods
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Ingestion  │  │  Validation │  │   Spark     │
│    Pod      │  │    Pod      │  │   Driver    │
│(orchestrator)│ │(orchestrator)│ │ (processing)│
└─────────────┘  └─────────────┘  └──────┬──────┘
                                         │ spawns
                         ┌───────────────┼───────────────┐
                         ▼               ▼               ▼
                  ┌───────────┐  ┌───────────┐  ┌───────────┐
                  │  Executor │  │  Executor │  │  Executor │
                  │    Pod    │  │    Pod    │  │    Pod    │
                  └───────────┘  └───────────┘  └───────────┘
```

### Spark on Kubernetes

Spark jobs are managed by the Spark Operator:
- Driver pod coordinates execution
- Executor pods scale based on workload
- Direct S3 access to MinIO for data I/O

## Storage Architecture

### MinIO Configuration

```yaml
Buckets:
  - airflow    # Airflow logs and artifacts
  - lakehouse  # Data lakehouse (Bronze/Silver/Gold)

Endpoints:
  Internal: minio.deepstorage.svc.cluster.local:9000
  External: LoadBalancer IP:9000
```

### Delta Lake Integration

Spark is configured with Delta Lake for:
- ACID transactions on object storage
- Time travel capabilities
- Schema evolution support

Configuration in SparkApplication manifests:
```yaml
sparkConf:
  spark.sql.extensions: "io.delta.sql.DeltaSparkSessionExtension"
  spark.sql.catalog.spark_catalog: "org.apache.spark.sql.delta.catalog.DeltaCatalog"
```

## GitOps Workflow

### ArgoCD Application Sync

```
GitHub Repository
       │
       │ git pull (every 3 min)
       ▼
┌─────────────────┐
│     ArgoCD      │
│   (cicd ns)     │
└────────┬────────┘
         │ kubectl apply
         ▼
┌─────────────────────────────────────┐
│         Kubernetes Cluster          │
│  ┌─────────┐ ┌─────────┐ ┌───────┐  │
│  │ Airflow │ │  Spark  │ │ MinIO │  │
│  └─────────┘ └─────────┘ └───────┘  │
└─────────────────────────────────────┘
```

### Sync Waves

ArgoCD sync waves ensure proper deployment order:
1. Secrets & Access Control (wave 1)
2. Databases (wave 2)
3. Core Services: Spark, Airflow (wave 3)
4. Reflector (wave 5)
5. MinIO, Grafana (wave 6)
6. Monitoring (wave 7)

## Security Model

### Secret Management

Secrets flow through Reflector for cross-namespace access:

```
┌─────────────────────────────────────────────────┐
│              Source Secrets                      │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │minio-secrets │  │ postgres-secrets         │ │
│  │(deepstorage) │  │ (database)               │ │
│  └──────┬───────┘  └───────────┬──────────────┘ │
│         │                      │                │
│         ▼    Reflector         ▼                │
│  ┌──────────────────────────────────────────┐   │
│  │           Replicated To:                 │   │
│  │  - processing (Spark access to MinIO)    │   │
│  │  - jupyter (JupyterLab access)           │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### RBAC Configuration

ClusterRoleBindings grant necessary permissions:
- `airflow-worker` ServiceAccount → cluster-admin (for pod creation)
- `default` ServiceAccount in processing → Spark executor management

## Monitoring Architecture

### Metrics Flow (In Development)

```
Airflow Pods (port 9091)
        │
        ▼
┌───────────────┐
│  Prometheus   │ ──► Scrapes metrics
│  (monitoring) │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│    Grafana    │ ──► Dashboards & Alerts
│  (monitoring) │
└───────────────┘
```

## Environment Portability

The architecture maintains portability across environments:

| Component | Minikube | EKS |
|-----------|----------|-----|
| Load Balancer | minikube tunnel | AWS ELB |
| Storage Class | standard | gp2 |
| Docker Registry | local (minikube docker-env) | DockerHub |
| DNS | cluster.local | cluster.local |

Key files that differ between environments:
- `manifests/deepstorage/minio.yaml` (storageClass)
- `manifests/database/postgres.yaml` (storageClass)
- `manifests/misc/*.yaml` (repository paths)

## Next Steps

- [Minikube Deployment](03-minikube-deployment.md) - Deploy locally
- [EKS Deployment](04-eks-deployment.md) - Deploy on AWS
