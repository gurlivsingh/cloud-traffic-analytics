"""One-command AWS deployment with CloudFormation (deploy/cloudformation.yaml).

    python deploy/aws.py up [--email you@example.com]   # create or update everything (~15-20 min first time)
    python deploy/aws.py status                         # website URL, health check, stack state
    python deploy/aws.py admin-password                 # show the dashboard's admin password (from SSM)
    python deploy/aws.py down                           # delete everything (asks first)

Credentials come from ~/.aws/credentials. In AWS Academy Learner Lab: Start Lab -> AWS Details ->
AWS CLI "Show" -> copy the whole block into that file (it expires when the lab session ends).
Own AWS account: add --instance-profile "" so the stack creates its own least-privilege IAM role.
"""
import argparse
import secrets
import sys
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from werkzeug.security import generate_password_hash

STACK = "traffic-analytics"
TEMPLATE = Path(__file__).with_name("cloudformation.yaml")
SECRETS = ["/traffic/db_password", "/traffic/flask_secret", "/traffic/admin_password", "/traffic/admin_password_hash"]


def _exists(ssm, name: str) -> bool:
    try:
        ssm.get_parameter(Name=name)
        return True
    except ssm.exceptions.ParameterNotFound:
        return False


def ensure_secrets(ssm) -> None:
    """Create random secrets once (SecureString). Never overwrite: RDS keeps using the first password."""
    def put(name, value, overwrite=False):
        ssm.put_parameter(Name=name, Value=value, Type="SecureString", Overwrite=overwrite)
        print(f"  created secret {name}")
    if not _exists(ssm, "/traffic/db_password"):
        put("/traffic/db_password", secrets.token_urlsafe(24))
    if not _exists(ssm, "/traffic/flask_secret"):
        put("/traffic/flask_secret", secrets.token_hex(32))
    if not (_exists(ssm, "/traffic/admin_password") and _exists(ssm, "/traffic/admin_password_hash")):
        pw = secrets.token_urlsafe(12)
        put("/traffic/admin_password", pw, overwrite=True)
        put("/traffic/admin_password_hash", generate_password_hash(pw), overwrite=True)


def stack(cf):
    try:
        return cf.describe_stacks(StackName=STACK)["Stacks"][0]
    except ClientError as e:
        if "does not exist" in str(e):
            return None
        raise


def wait(cf, since: float) -> str:
    """Print stack events as they happen until the stack leaves *_IN_PROGRESS."""
    seen = set()
    while True:
        events = cf.describe_stack_events(StackName=STACK)["StackEvents"]
        for e in reversed(events):
            if e["EventId"] in seen or e["Timestamp"].timestamp() < since:
                continue
            seen.add(e["EventId"])
            reason = f"  ({e['ResourceStatusReason']})" if e.get("ResourceStatusReason") else ""
            print(f"  {e['Timestamp']:%H:%M:%S}  {e['LogicalResourceId']:<22} {e['ResourceStatus']}{reason}")
        s = stack(cf)
        status = s["StackStatus"] if s else "DELETE_COMPLETE"
        if not status.endswith("_IN_PROGRESS"):
            return status
        time.sleep(15)


def outputs(cf) -> dict:
    s = stack(cf)
    return {o["OutputKey"]: o["OutputValue"] for o in (s or {}).get("Outputs", [])}


def cmd_up(args, sess):
    cf, ssm = sess.client("cloudformation"), sess.client("ssm")
    print("Secrets (SSM Parameter Store):")
    ensure_secrets(ssm)
    params = [{"ParameterKey": "InstanceProfileName", "ParameterValue": args.instance_profile},
              {"ParameterKey": "AlertEmail", "ParameterValue": args.email}]
    kw = dict(StackName=STACK, TemplateBody=TEMPLATE.read_text(), Parameters=params,
              Capabilities=[] if args.instance_profile else ["CAPABILITY_IAM"])
    since = time.time() - 5
    if stack(cf) is None:
        print(f"Creating stack {STACK} (RDS alone takes ~10 min; the server then installs and loads data)...")
        cf.create_stack(**kw, OnFailure="DO_NOTHING", Tags=[{"Key": "project", "Value": "traffic-analytics"}])
    else:
        print(f"Updating stack {STACK}...")
        try:
            cf.update_stack(**kw)
        except ClientError as e:
            if "No updates are to be performed" in str(e):
                print("Nothing to change.")
                return cmd_status(args, sess)
            raise
    status = wait(cf, since)
    print(f"\nStack status: {status}")
    if status not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
        sys.exit("Deployment failed - see the events above. Fix, then run `down` and `up` again.")
    cmd_status(args, sess)


def cmd_status(args, sess):
    cf = sess.client("cloudformation")
    s = stack(cf)
    if s is None:
        print("Not deployed.")
        return
    print(f"Stack {STACK}: {s['StackStatus']}")
    out = outputs(cf)
    for k, v in out.items():
        print(f"  {k:<20} {v}")
    url = out.get("WebsiteUrl")
    if url:
        try:
            with urllib.request.urlopen(url + "/health", timeout=10) as r:
                print(f"  health               {r.status} {r.read().decode()}")
        except Exception as e:  # noqa: BLE001 - report, don't crash
            print(f"  health               not reachable yet ({e})")


def cmd_admin_password(args, sess):
    v = sess.client("ssm").get_parameter(Name="/traffic/admin_password", WithDecryption=True)
    print(v["Parameter"]["Value"])


def cmd_down(args, sess):
    cf = sess.client("cloudformation")
    if stack(cf) is None:
        print("Nothing deployed.")
        return
    if not args.yes and input(f"Delete stack {STACK}, its database, bucket and all data? Type 'delete': ") != "delete":
        print("Cancelled.")
        return
    bucket = outputs(cf).get("DataBucketName")
    if bucket:
        print(f"Emptying s3://{bucket} (all versions)...")
        sess.resource("s3").Bucket(bucket).object_versions.delete()
    since = time.time() - 5
    cf.delete_stack(StackName=STACK)
    status = wait(cf, since)
    print(f"Stack status: {status}")
    if status == "DELETE_COMPLETE":
        ssm = sess.client("ssm")
        for name in SECRETS:
            try:
                ssm.delete_parameter(Name=name)
            except ssm.exceptions.ParameterNotFound:
                pass
        print("Secrets deleted. Everything is gone.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["up", "status", "admin-password", "down"])
    ap.add_argument("--region", default=None, help="default: from ~/.aws/config, else us-east-1")
    ap.add_argument("--email", default="", help="send CloudWatch alarm emails here")
    ap.add_argument("--instance-profile", default="LabInstanceProfile",
                    help='existing EC2 instance profile; "" = create a least-privilege role')
    ap.add_argument("--yes", action="store_true", help="skip the confirmation for `down`")
    args = ap.parse_args()

    sess = boto3.Session(region_name=args.region or boto3.Session().region_name or "us-east-1")
    try:
        who = sess.client("sts").get_caller_identity()
    except (NoCredentialsError, ClientError) as e:
        sys.exit(f"No working AWS credentials ({e}). See the instructions at the top of this file.")
    print(f"AWS account {who['Account']} · region {sess.region_name}")
    {"up": cmd_up, "status": cmd_status, "admin-password": cmd_admin_password, "down": cmd_down}[args.command](args, sess)


if __name__ == "__main__":
    main()
