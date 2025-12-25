# Troubleshooting

This guide covers common issues and their solutions when operating the K8s Data Platform.

## Quick Diagnostics

Run this checklist when things aren't working:

```bash
# 1. Check all pods
kubectl get pods -A | grep -v Running | grep -v Completed

# 2. Check ArgoCD sync status
argocd app list

# 3. Check recent events
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

# 4. Check node resources
kubectl top nodes
kubectl top pods -A
```

## Common Issues

### ArgoCD

#### Application Stuck in "Progressing"

**Symptoms:** ArgoCD shows application as "Progressing" indefinitely.

**Diagnosis:**
```bash
argocd app get <app-name>
kubectl describe application <app-name> -n cicd
```

**Solutions:**
1. Force sync:
   ```bash
   argocd app sync <app-name> --force
   ```
2. Check for resource issues:
   ```bash
   kubectl get events -n <target-namespace>
   ```
3. Delete and re-apply:
   ```bash
   argocd app delete <app-name>
   kubectl apply -f <manifest-path>
   ```

#### Repository Connection Failed

**Symptoms:** "repository not accessible" error.

**Diagnosis:**
```bash
argocd repo list
```

**Solutions:**
1. Re-add repository:
   ```bash
   argocd repo rm git@github.com:user/repo.git
   argocd repo add git@github.com:user/repo.git --ssh-private-key-path ~/.ssh/id_ed25519 --insecure-skip-server-verification
   ```
2. Verify SSH key:
   ```bash
   ssh -T git@github.com
   ```

### Airflow

#### DAGs Not Appearing

**Symptoms:** DAGs don't show in Airflow UI.

**Diagnosis:**
```bash
# Check git-sync logs
kubectl logs -n orchestrator -l component=scheduler -c git-sync

# Check DAGs folder
kubectl exec -n orchestrator $(kubectl get pods -n orchestrator -l component=scheduler -o jsonpath='{.items[0].metadata.name}') -c scheduler -- ls /opt/airflow/dags
```

**Solutions:**
1. Check SSH secret:
   ```bash
   kubectl get secret airflow-ssh-secret -n orchestrator
   ```
2. Recreate SSH secret:
   ```bash
   kubectl delete secret airflow-ssh-secret -n orchestrator
   kubectl create secret generic airflow-ssh-secret --from-file=gitSshKey=$HOME/.ssh/id_ed25519 -n orchestrator
   ```
3. Restart scheduler:
   ```bash
   kubectl rollout restart deployment -n orchestrator -l component=scheduler
   ```

#### Tasks Stuck in "Queued"

**Symptoms:** Tasks remain in queued state, never start.

**Diagnosis:**
```bash
# Check worker pods
kubectl get pods -n orchestrator

# Check scheduler logs
kubectl logs -n orchestrator -l component=scheduler --tail=100
```

**Solutions:**
1. Check RBAC:
   ```bash
   kubectl auth can-i create pods -n orchestrator --as=system:serviceaccount:orchestrator:airflow-worker
   ```
2. Reapply access controls:
   ```bash
   kubectl apply -f <env>/manifests/misc/access-control.yaml
   ```

#### Database Connection Errors

**Symptoms:** "connection refused" to PostgreSQL.

**Diagnosis:**
```bash
kubectl get pods -n database
kubectl logs -n database -l app.kubernetes.io/name=postgresql
```

**Solutions:**
1. Check PostgreSQL is running:
   ```bash
   kubectl get pods -n database
   ```
2. Verify connection string:
   ```bash
   kubectl get secret airflow-metadata-secret -n orchestrator -o jsonpath='{.data.connection}' | base64 -d
   ```
3. Test connection:
   ```bash
   kubectl run pg-test --rm -it --image=postgres:12 --restart=Never -- psql "postgresql://user:pass@postgres-postgresql.database.svc.cluster.local:5432/airflow"
   ```

### Spark

#### SparkApplication Stuck in "Pending"

**Symptoms:** Spark application never starts.

**Diagnosis:**
```bash
kubectl describe sparkapplication <name> -n processing
kubectl get events -n processing
```

**Solutions:**
1. Check driver pod:
   ```bash
   kubectl get pods -n processing -l spark-role=driver
   kubectl describe pod <driver-pod> -n processing
   ```
2. Check image pull:
   ```bash
   kubectl get events -n processing | grep -i pull
   ```
3. Verify secrets:
   ```bash
   kubectl get secret minio-secrets -n processing
   ```

#### Executor Pods Failing

**Symptoms:** Executors crash with OOM or connection errors.

**Diagnosis:**
```bash
kubectl logs -n processing -l spark-role=executor --tail=200
```

**Solutions:**
1. Increase memory:
   ```yaml
   executor:
     memory: "1g"  # Increase from 512m
   ```
2. Check MinIO connectivity:
   ```bash
   kubectl run test --rm -it --image=curlimages/curl --restart=Never -- curl http://minio.deepstorage.svc.cluster.local:9000
   ```

#### S3 Access Denied

**Symptoms:** "Access Denied" when reading/writing to MinIO.

**Diagnosis:**
```bash
kubectl logs -n processing -l spark-role=driver | grep -i denied
```

**Solutions:**
1. Verify credentials in executor:
   ```bash
   kubectl exec -n processing <driver-pod> -- env | grep AWS
   ```
2. Check secret reflection:
   ```bash
   kubectl get secret minio-secrets -n processing
   ```
3. Recreate secret:
   ```bash
   kubectl get secret minio-secrets -n deepstorage -o yaml | sed 's/namespace: deepstorage/namespace: processing/' | kubectl apply -f -
   ```

### MinIO

#### Pods Stuck in Pending

**Symptoms:** MinIO pods won't start.

**Diagnosis:**
```bash
kubectl describe pod -n deepstorage -l app.kubernetes.io/name=minio
kubectl get pvc -n deepstorage
```

**Solutions:**
1. Check storage class:
   ```bash
   kubectl get storageclass
   ```
2. For Minikube, enable storage addon:
   ```bash
   minikube addons enable storage-provisioner
   ```
3. For EKS, verify gp2 is available:
   ```bash
   kubectl get storageclass gp2
   ```

#### Cannot Access Web Console

**Symptoms:** MinIO UI unreachable.

**Diagnosis:**
```bash
kubectl get svc -n deepstorage
kubectl get endpoints -n deepstorage
```

**Solutions:**
1. Check LoadBalancer (Minikube):
   ```bash
   minikube tunnel  # Must be running
   ```
2. Port forward as workaround:
   ```bash
   kubectl port-forward svc/minio -n deepstorage 9000:9000
   ```

### Reflector

#### Secrets Not Replicated

**Symptoms:** Secrets missing in target namespaces.

**Diagnosis:**
```bash
kubectl get secret minio-secrets -n processing
kubectl logs -n management -l app.kubernetes.io/name=reflector
```

**Solutions:**
1. Check annotations on source secret:
   ```bash
   kubectl get secret minio-secrets -n deepstorage -o yaml | grep reflector
   ```
2. Verify namespace is in allowed list:
   ```yaml
   annotations:
     reflector.v1.k8s.emberstack.com/reflection-allowed-namespaces: "deepstorage,processing,jupyter"
   ```
3. Restart Reflector:
   ```bash
   kubectl rollout restart deployment -n management -l app.kubernetes.io/name=reflector
   ```

### Kubernetes General

#### ImagePullBackOff

**Symptoms:** Pod stuck in ImagePullBackOff state.

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
```

**Solutions:**
1. For Minikube, use local images:
   ```bash
   eval $(minikube docker-env)
   docker build -t <image-name> .
   ```
2. Set `imagePullPolicy: IfNotPresent` in manifests
3. For EKS, push images to registry:
   ```bash
   docker push <registry>/<image>:<tag>
   ```

#### Node Resource Pressure

**Symptoms:** Pods evicted, scheduling fails.

**Diagnosis:**
```bash
kubectl describe nodes | grep -A5 "Allocated resources"
kubectl top nodes
```

**Solutions:**
1. For Minikube:
   ```bash
   minikube stop
   minikube start --memory=12000 --cpus=4
   ```
2. For EKS, scale node group:
   - Edit Terraform variables or use AWS console

### JupyterLab

#### Cannot Connect to MinIO

**Symptoms:** Connection timeout in notebooks.

**Diagnosis:**
```bash
kubectl logs -n jupyter -l app=custom-jupyter
kubectl get endpoints minio -n deepstorage
```

**Solutions:**
1. Verify environment variables:
   ```bash
   kubectl exec -n jupyter $(kubectl get pods -n jupyter -l app=custom-jupyter -o jsonpath='{.items[0].metadata.name}') -- env | grep MINIO
   ```
2. Check DNS resolution:
   ```bash
   kubectl exec -n jupyter $(kubectl get pods -n jupyter -l app=custom-jupyter -o jsonpath='{.items[0].metadata.name}') -- nslookup minio.deepstorage.svc.cluster.local
   ```

## Log Collection

### Collect All Logs

```bash
# Create logs directory
mkdir -p logs/$(date +%Y%m%d)

# Airflow
kubectl logs -n orchestrator -l component=scheduler --tail=1000 > logs/$(date +%Y%m%d)/airflow-scheduler.log
kubectl logs -n orchestrator -l component=webserver --tail=1000 > logs/$(date +%Y%m%d)/airflow-webserver.log

# Spark
kubectl logs -n processing -l spark-role=driver --tail=1000 > logs/$(date +%Y%m%d)/spark-driver.log

# MinIO
kubectl logs -n deepstorage -l app.kubernetes.io/name=minio --tail=1000 > logs/$(date +%Y%m%d)/minio.log

# ArgoCD
kubectl logs -n cicd -l app.kubernetes.io/name=argocd-server --tail=1000 > logs/$(date +%Y%m%d)/argocd.log
```

## Getting Help

If issues persist:

1. Check ArgoCD application events
2. Review Kubernetes events: `kubectl get events -A --sort-by='.lastTimestamp'`
3. Collect logs using the script above
4. Open an issue on the repository with:
   - Environment (Minikube/EKS)
   - Steps to reproduce
   - Relevant logs
   - Expected vs actual behavior
