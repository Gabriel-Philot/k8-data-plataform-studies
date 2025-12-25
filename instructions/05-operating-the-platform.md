# Operating the Platform

This guide covers day-to-day operations, running pipelines, and monitoring the K8s Data Platform.

## Data Pipeline Overview

The platform runs a brewery data pipeline with two main DAGs:

| DAG | Purpose | Trigger |
|-----|---------|---------|
| `brewapi-ingestion-validation-minio` | Ingest API data, validate, store in Bronze | Scheduled (@daily) |
| `brew-process-transformation` | Transform Bronze → Silver → Gold | Dataset trigger |

## Running Pipelines

### Via Airflow UI

1. Access Airflow at `http://<AIRFLOW_IP>:8080`
2. Login with `admin/admin`
3. Enable the DAG by toggling the switch
4. Click "Trigger DAG" to run manually

### Via Airflow CLI

```bash
# Get scheduler pod name
SCHEDULER=$(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}')

# Trigger a DAG
kubectl exec -n orchestrator $SCHEDULER -- airflow dags trigger brewapi-ingestion-validation-minio

# Check DAG status
kubectl exec -n orchestrator $SCHEDULER -- airflow dags list-runs -d brewapi-ingestion-validation-minio
```

### Manual Spark Job Execution

Run Spark jobs directly without Airflow:

```bash
# Bronze to Silver transformation
kubectl apply -f dags/spark_jobs/bronze_to_silver.yaml -n processing

# Check Spark application status
kubectl get sparkapplication -n processing

# View Spark driver logs
kubectl logs -n processing -l spark-role=driver --tail=100
```

## Monitoring Pipeline Execution

### Airflow Task Logs

```bash
# List running tasks
kubectl get pods -n orchestrator

# View task logs
kubectl logs -n orchestrator <pod-name>
```

### Spark Job Logs

```bash
# List Spark applications
kubectl get sparkapplication -n processing

# Describe Spark application
kubectl describe sparkapplication bronze-to-silver -n processing

# View driver logs
kubectl logs -n processing $(kubectl get pods -n processing -l spark-role=driver -o jsonpath='{.items[0].metadata.name}')
```

### XCom Validation Results

The validation DAG stores results in XCom:

```bash
SCHEDULER=$(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}')

# Check XCom values
kubectl exec -n orchestrator $SCHEDULER -- airflow tasks test brewapi-ingestion-validation-minio validation_xcom_pull 2024-01-01
```

## Data Exploration with JupyterLab

### Connect to MinIO from JupyterLab

The JupyterLab image is pre-configured with MinIO credentials via environment variables.

Sample DuckDB query:

```python
import duckdb

# Configure S3 connection
conn = duckdb.connect()
conn.execute("""
    INSTALL httpfs;
    LOAD httpfs;
    SET s3_endpoint='minio.deepstorage.svc.cluster.local:9000';
    SET s3_access_key_id='miniouser';
    SET s3_secret_access_key='miniosecret';
    SET s3_use_ssl=false;
    SET s3_url_style='path';
""")

# Query Bronze layer
df = conn.execute("""
    SELECT * FROM read_parquet('s3://lakehouse/bronze/*/*/*.parquet')
    LIMIT 100
""").df()
```

### Query Delta Tables

```python
from deltalake import DeltaTable

# Read Delta table
dt = DeltaTable(
    "s3://lakehouse/silver/breweries",
    storage_options={
        "AWS_ENDPOINT_URL": "http://minio.deepstorage.svc.cluster.local:9000",
        "AWS_ACCESS_KEY_ID": "miniouser",
        "AWS_SECRET_ACCESS_KEY": "miniosecret",
        "AWS_REGION": "us-east-1",
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true"
    }
)

df = dt.to_pandas()
```

## Data Validation

### Check Record Counts

The validation step compares record counts between API and Bronze layer:

| Validation | Condition | Result |
|------------|-----------|--------|
| Pass | API count = Bronze count | Triggers processing DAG |
| Fail | Count mismatch | Logs warning, skips processing |

### Manual Validation

```bash
# Count records in MinIO
MINIO_IP=$(kubectl get services -n deepstorage -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')

# Using MinIO client
mc alias set minio http://$MINIO_IP:9000 miniouser miniosecret
mc ls minio/lakehouse/bronze/ --recursive | wc -l
```

## Common Operations

### Restart a Failed DAG Run

```bash
SCHEDULER=$(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}')

# Clear failed tasks
kubectl exec -n orchestrator $SCHEDULER -- airflow tasks clear brewapi-ingestion-validation-minio -s 2024-01-01 -e 2024-01-02

# Re-trigger
kubectl exec -n orchestrator $SCHEDULER -- airflow dags trigger brewapi-ingestion-validation-minio
```

### Scale Spark Executors

Edit the SparkApplication manifest:

```yaml
executor:
  instances: 5  # Increase from default 3
  cores: 2
  memory: "1g"
```

Apply changes:

```bash
kubectl apply -f dags/spark_jobs/bronze_to_silver.yaml -n processing
```

### Update DAGs

DAGs sync automatically via GitSync. Force a sync:

```bash
# Find gitsync container
kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}'

# Trigger sync
kubectl exec -n orchestrator <scheduler-pod> -c git-sync -- sh -c "git fetch && git reset --hard origin/main"
```

### View MinIO Bucket Contents

```bash
# Get MinIO IP
MINIO_IP=$(kubectl get services -n deepstorage -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')

# Using MinIO web console
echo "http://$MINIO_IP:9000"

# Or via CLI
mc alias set minio http://$MINIO_IP:9000 miniouser miniosecret
mc ls minio/lakehouse/
mc ls minio/lakehouse/bronze/
mc ls minio/lakehouse/silver/
mc ls minio/lakehouse/gold/
```

## Health Checks

### Quick Status Check

```bash
# All pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# ArgoCD sync status
argocd app list

# Airflow health
kubectl exec -n orchestrator $(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}') -- airflow jobs check
```

### Component Status

```bash
# Airflow
kubectl get pods -n orchestrator

# Spark Operator
kubectl get pods -n processing

# MinIO
kubectl get pods -n deepstorage

# PostgreSQL
kubectl get pods -n database
```

## Backup and Recovery

### Export Airflow Variables/Connections

```bash
SCHEDULER=$(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}')

# Export connections
kubectl exec -n orchestrator $SCHEDULER -- airflow connections export /tmp/connections.json
kubectl cp orchestrator/$SCHEDULER:/tmp/connections.json ./connections-backup.json

# Export variables
kubectl exec -n orchestrator $SCHEDULER -- airflow variables export /tmp/variables.json
kubectl cp orchestrator/$SCHEDULER:/tmp/variables.json ./variables-backup.json
```

### MinIO Data Backup

```bash
mc alias set minio http://$MINIO_IP:9000 miniouser miniosecret
mc mirror minio/lakehouse ./lakehouse-backup/
```

## Performance Tuning

### Spark Configuration

Key settings in SparkApplication manifests:

```yaml
driver:
  cores: 1
  memory: "512m"
executor:
  cores: 1
  instances: 3
  memory: "512m"
```

For larger datasets:

```yaml
driver:
  cores: 2
  memory: "2g"
executor:
  cores: 2
  instances: 5
  memory: "2g"
```

### Airflow Configuration

Adjust worker resources in `airflow.yaml`:

```yaml
workers:
  resources:
    limits:
      cpu: 2
      memory: 4Gi
    requests:
      cpu: 1
      memory: 2Gi
```

## Next Steps

- [Troubleshooting](06-troubleshooting.md) - Common issues and solutions
- [Architecture](02-architecture.md) - Deep dive into components
