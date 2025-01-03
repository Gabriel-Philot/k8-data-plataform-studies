#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
This is an example DAG which uses SparkKubernetesOperator and SparkKubernetesSensor.
In this example, we create two tasks which execute sequentially.
The first task is to submit sparkApplication on Kubernetes cluster(the example uses
spark-pi application).
and the second task is to check the final state of the sparkApplication that submitted
in the first state.
Spark-on-k8s operator is required to be already installed on Kubernetes
https://github.com/GoogleCloudPlatform/spark-on-k8s-operator
"""

from datetime import timedelta

# [START import_module]
# The DAG object; we'll need this to instantiate a DAG
from airflow import DAG, Dataset
from airflow.operators.dummy_operator import DummyOperator
from airflow.providers.amazon.aws.operators.s3 import S3ListOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor, S3KeysUnchangedSensor

# Operators; we need this to operate!
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import (
    SparkKubernetesOperator,
)
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import (
    SparkKubernetesSensor,
)
from airflow.utils.dates import days_ago

# [END import_module]

dataset = Dataset("s3://brew-api/ingestion-validation")

# [START default_args]
# These args will get passed on to each operator
# You can override them on a per-task basis during operator initialization
default_args = {
    "owner": "GabrielPhilot",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "email": ["bilphilot@gmail.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "max_active_runs": 1,
    "retries": 1,
    "retry_delay": timedelta(1),
}
# [END default_args]

# [START instantiate_dag]

dag = DAG(
    "brew-process-transformation",
    default_args=default_args,
    schedule=[dataset],
    tags=["spark", "kubernetes", "s3", "sensor", "minio", "bronze", "silver"],
)
# [END instantiate_dag]

# [START set_tasks]

start = DummyOperator(task_id='start', dag=dag)

# verify if new data has arrived on processing bucket
# connecting to minio to check (sensor)
list_keys = S3ListOperator(
    task_id="list_keys",
    bucket="lakehouse",
    prefix="bronze/",
    aws_conn_id="minio",
    do_xcom_push=True,
    dag=dag,
)


tranform = SparkKubernetesOperator(
    task_id="bronze_to_silver_task",
    namespace="processing",
    application_file="spark_jobs/bronze_to_silver.yaml",
    kubernetes_conn_id="kubernetes_default",
    do_xcom_push=True,
    dag=dag,
)

transform_sensor = SparkKubernetesSensor(
    task_id="bronze_to_silver_task_monitor",
    namespace="processing",
    application_name="{{task_instance.xcom_pull(task_ids='bronze_to_silver_task')['metadata']['name']}}",
    kubernetes_conn_id="kubernetes_default",
    dag=dag,
    attach_log=True,
)

gold_delivery = SparkKubernetesOperator(
    task_id="silver_to_gold_task",
    namespace="processing",
    application_file="spark_jobs/silver_to_gold.yaml",
    kubernetes_conn_id="kubernetes_default",
    do_xcom_push=True,
    dag=dag,
)

gold_delivery_sensor = SparkKubernetesSensor(
    task_id="silver_to_gold_task_monitor",
    namespace="processing",
    application_name="{{task_instance.xcom_pull(task_ids='silver_to_gold_task')['metadata']['name']}}",
    kubernetes_conn_id="kubernetes_default",
    dag=dag,
    attach_log=True,
)


end = DummyOperator(task_id='end', dag=dag)
# [END set_tasks]
# [START task_sequence]
(
    start
    >> list_keys
    >> tranform
    >> transform_sensor
    >> gold_delivery
    >> gold_delivery_sensor
    >> end
)
# [END task_sequence]
