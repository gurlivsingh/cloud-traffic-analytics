"""Thin wrappers around AWS services: S3 storage, SSM secrets, CloudWatch metrics.

Every function has a local fallback so the project runs without AWS.
On EC2, credentials come from the instance IAM role - no access keys anywhere.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import config

log = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _client(name):
    import boto3
    return boto3.client(name, region_name=config.AWS_REGION)


# ---------- Object storage: S3 bucket, or ./storage locally ----------

def put_bytes(key: str, data: bytes) -> None:
    if config.S3_BUCKET:
        _client("s3").put_object(Bucket=config.S3_BUCKET, Key=key, Body=data)
    else:
        p = config.LOCAL_STORAGE / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def get_bytes(key: str) -> bytes:
    if config.S3_BUCKET:
        return _client("s3").get_object(Bucket=config.S3_BUCKET, Key=key)["Body"].read()
    return (config.LOCAL_STORAGE / key).read_bytes()


def list_keys(prefix: str) -> list[str]:
    if config.S3_BUCKET:
        keys = []
        for page in _client("s3").get_paginator("list_objects_v2").paginate(Bucket=config.S3_BUCKET, Prefix=prefix):
            keys += [o["Key"] for o in page.get("Contents", [])]
        return sorted(keys)
    base = config.LOCAL_STORAGE
    return sorted(p.relative_to(base).as_posix() for p in (base / prefix).rglob("*") if p.is_file()) \
        if (base / prefix).exists() else []


def storage_ok() -> bool:
    try:
        if config.S3_BUCKET:
            _client("s3").head_bucket(Bucket=config.S3_BUCKET)
        return True
    except Exception as e:  # noqa: BLE001 - health check reports, never raises
        log.warning("storage check failed: %s", e)
        return False


# ---------- Secrets: env var, then SSM Parameter Store ----------

def get_secret(env_var: str, ssm_param: str) -> str | None:
    if os.getenv(env_var):
        return os.environ[env_var]
    if not (config.S3_BUCKET or config.DB_HOST):   # not on AWS
        return None
    try:
        return _client("ssm").get_parameter(Name=ssm_param, WithDecryption=True)["Parameter"]["Value"]
    except Exception as e:  # noqa: BLE001
        log.error("could not read SSM parameter %s: %s", ssm_param, e)
        return None


# ---------- CloudWatch ----------

def put_metric(name: str, value: float, unit: str = "Count") -> None:
    if not config.EC2_INSTANCE_ID:
        log.info("metric %s=%s (CloudWatch disabled locally)", name, value)
        return
    try:
        _client("cloudwatch").put_metric_data(
            Namespace=config.METRIC_NAMESPACE,
            MetricData=[{"MetricName": name, "Value": float(value), "Unit": unit}])
    except Exception as e:  # noqa: BLE001 - monitoring must never break the pipeline
        log.warning("put_metric failed: %s", e)


def system_metrics(hours: int = 3) -> dict:
    """Recent EC2/RDS/custom metrics for the dashboard's System page."""
    if not config.EC2_INSTANCE_ID:
        return {"available": False}
    ec2 = [{"Name": "InstanceId", "Value": config.EC2_INSTANCE_ID}]
    rds = [{"Name": "DBInstanceIdentifier", "Value": config.RDS_INSTANCE_ID}]
    queries = [
        ("ec2_cpu", "EC2 CPU % (CloudWatch Agent)", "CWAgent", "cpu_usage_active", ec2, "Average"),
        ("ec2_mem", "EC2 memory % (CloudWatch Agent)", "CWAgent", "mem_used_percent", ec2, "Average"),
        ("rds_cpu", "RDS CPU %", "AWS/RDS", "CPUUtilization", rds, "Average"),
        ("rds_conn", "RDS connections", "AWS/RDS", "DatabaseConnections", rds, "Average"),
        ("rows", "Rows loaded by pipeline", config.METRIC_NAMESPACE, "RowsLoaded", [], "Sum"),
    ]
    end = datetime.now(timezone.utc)
    try:
        resp = _client("cloudwatch").get_metric_data(
            StartTime=end - timedelta(hours=hours), EndTime=end, ScanBy="TimestampAscending",
            MetricDataQueries=[{
                "Id": qid, "Label": label,
                "MetricStat": {"Metric": {"Namespace": ns, "MetricName": m, "Dimensions": dims},
                               "Period": 60, "Stat": stat}} for qid, label, ns, m, dims, stat in queries])
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)}
    return {"available": True, "series": [
        {"label": r["Label"], "t": [t.strftime("%H:%M") for t in r["Timestamps"]], "v": r["Values"]}
        for r in resp["MetricDataResults"]]}
