"""Point every test at a throwaway SQLite DB + storage folder (set before any project import)."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="traffic-test-"))
os.environ.update(LOCAL_STORAGE=str(_tmp / "storage"), SQLITE_PATH=str(_tmp / "test.db"),
                  S3_BUCKET="", DB_HOST="", EC2_INSTANCE_ID="", FLASK_SECRET="test", ADMIN_PASSWORD_HASH="")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
