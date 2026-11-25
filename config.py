"""Settings from environment variables (or a local .env file).

Locally (no AWS vars set) everything falls back to SQLite + a ./storage folder,
so the whole project runs on a laptop. On EC2 the same code uses S3, RDS, SSM and CloudWatch.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Load .env without an extra dependency: KEY=VALUE lines, real env vars win.
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")              # empty -> local ./storage folder
LOCAL_STORAGE = Path(os.getenv("LOCAL_STORAGE", ROOT / "storage"))

DB_HOST = os.getenv("DB_HOST", "")                  # empty -> local SQLite
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", ROOT / "local.db"))
DB_NAME = os.getenv("DB_NAME", "traffic")
DB_USER = os.getenv("DB_USER", "traffic_admin")
DB_PASSWORD_PARAM = os.getenv("DB_PASSWORD_PARAM", "/traffic/db_password")

# Admin login + Flask session key: env var first, then SSM Parameter Store.
ADMIN_PASSWORD_HASH_PARAM = os.getenv("ADMIN_PASSWORD_HASH_PARAM", "/traffic/admin_password_hash")
FLASK_SECRET_PARAM = os.getenv("FLASK_SECRET_PARAM", "/traffic/flask_secret")

# For the System page (CloudWatch). Empty -> page says "not running on AWS".
EC2_INSTANCE_ID = os.getenv("EC2_INSTANCE_ID", "")
RDS_INSTANCE_ID = os.getenv("RDS_INSTANCE_ID", "")
METRIC_NAMESPACE = "TrafficAnalytics"

PIPELINE_LOG = Path(os.getenv("PIPELINE_LOG", ROOT / "pipeline.log"))  # where the admin page's runs log
PREDICT_HOURS = 6
MAX_UPLOAD_MB = 20
