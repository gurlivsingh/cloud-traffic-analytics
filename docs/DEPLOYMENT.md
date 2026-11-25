# Deploying on AWS

Step-by-step guide to running the project on AWS in region **ap-south-1 (Mumbai)**. Each step takes a few minutes in
the AWS console. When everything is running, work through [Security checks](#9-security-checks) and record each
result as evidence for the report (see [REQUIREMENTS.md](REQUIREMENTS.md), deliverable D4).

> **AWS Academy Learner Lab?** You can't create IAM roles there. In step 5, attach the ready-made
> **`LabInstanceProfile`** instead, and skip step 0's IAM users. Instances stop when the lab session ends, so start the
> lab about 30 minutes before a demo. An Elastic IP keeps the address the same.

## 0. Safety first
- Root account: turn on MFA.
- IAM: create one user per member in a `developers` group. Never use the root account day to day.
- Billing → Budgets: create a **$1** and a **$5** budget with email alerts.

## 1. S3 bucket
- Create bucket `traffic-analytics-<yourname>-<random>`.
- Block *all* public access: on. Default encryption SSE-S3: on. Bucket versioning: on.

## 2. Secrets in SSM Parameter Store
Systems Manager → Parameter Store → Create parameter, type **SecureString**:

| Name | Value |
|---|---|
| `/traffic/db_password` | A strong password. You'll use the same one for RDS in step 4 |
| `/traffic/admin_password_hash` | Output of `python -c "from werkzeug.security import generate_password_hash as g; print(g('YOUR-ADMIN-PASSWORD'))"` |
| `/traffic/flask_secret` | Output of `python -c "import secrets; print(secrets.token_hex(32))"` |

## 3. Security groups
VPC → Security groups (default VPC):
- **`traffic-ec2-sg`** inbound:
  - HTTP 80 from `0.0.0.0/0`
  - SSH 22 from **My IP** only (or no SSH at all, and connect with EC2 Instance Connect or Session Manager)
- **`traffic-rds-sg`** inbound: PostgreSQL 5432, with **source = `traffic-ec2-sg`** (the security group, not an IP range).

## 4. RDS (PostgreSQL)
- Create database → Standard create → **PostgreSQL** → Template **Free tier**.
- Identifier `traffic-db`, master username `traffic_admin`, password = the value of `/traffic/db_password`.
- Instance class db.t3.micro (or db.t4g.micro), 20 GB gp2, storage autoscaling off.
- **Public access: No.** Security group: `traffic-rds-sg`.
- Additional configuration: **Initial database name `traffic`**, backup retention 1 day, Performance Insights and Enhanced Monitoring off.
- Copy the **endpoint** once the database is available.

## 5. IAM role for EC2
- IAM → Roles → Create → trusted entity **AWS service: EC2**.
- Attach the managed policy **`CloudWatchAgentServerPolicy`**.
- Add an inline policy from [`deploy/iam-ec2-policy.json`](../deploy/iam-ec2-policy.json), replacing `YOUR_BUCKET_NAME` and `YOUR_ACCOUNT_ID`. It allows only:
  - read and write in this one bucket
  - reading `/traffic/*` parameters
  - writing and reading CloudWatch metrics
- Name the role `traffic-ec2-role`.

## 6. EC2
- Launch instance: **Amazon Linux 2023**, **t3.micro**, 20 GB gp3, security group `traffic-ec2-sg`.
- Advanced details → IAM instance profile **`traffic-ec2-role`** (or `LabInstanceProfile` on Learner Lab).
- Allocate an **Elastic IP** and associate it with the instance.

## 7. Install the application
Connect with EC2 Instance Connect, then:
```bash
sudo dnf install -y git
sudo git clone https://github.com/<owner>/<repo>.git /opt/traffic
cd /opt/traffic
sudo bash deploy/setup_ec2.sh          # 1st run creates .env
sudo nano .env                         # set S3_BUCKET, DB_HOST (RDS endpoint), RDS_INSTANCE_ID=traffic-db
sudo bash deploy/setup_ec2.sh          # 2nd run installs everything; ends with a /health check
sudo -u ec2-user .venv/bin/python -m pipeline.prepare_data    # dataset -> S3
sudo -u ec2-user .venv/bin/python -m pipeline.run_all         # S3 -> RDS, train, predict (a few minutes)
```
For a private repository, clone with a GitHub personal access token, or make the repository public before cloning.

`setup_ec2.sh` does the following:
- adds 2 GB of swap
- installs Python 3.11, nginx, the CloudWatch Agent, the PostgreSQL client and cron
- creates the virtual environment
- writes the instance id into `.env`
- installs the systemd service (gunicorn, running as `ec2-user`) and the nginx reverse proxy
- installs the cron schedule (hourly predictions, nightly retraining)
- starts the CloudWatch Agent

Open `http://<elastic-ip>/`. To update after a `git push`, run:
`cd /opt/traffic && sudo git pull && sudo bash deploy/setup_ec2.sh`.

## 8. Monitoring
Open **CloudShell** from the console's top bar, upload [`deploy/create_monitoring.sh`](../deploy/create_monitoring.sh), and run:
```bash
bash create_monitoring.sh you@example.com i-0123456789abcdef0 traffic-db
```
It creates:
- an SNS email topic (confirm the subscription email)
- three alarms: EC2 CPU > 70% for 2 min, RDS free storage < 2 GB, and any ETL failure
- the **TrafficAnalytics** CloudWatch dashboard
- 7-day retention on the app's log groups

## 9. Security checks
Screenshot each one for the report.

| Check | Expected |
|---|---|
| `psql -h <rds-endpoint> -U traffic_admin traffic` from your laptop | Times out (RDS is not public) |
| Same command from the EC2 instance | Connects |
| Open `https://<bucket>.s3.ap-south-1.amazonaws.com/raw/history.csv.gz` | AccessDenied |
| `aws s3 ls s3://<bucket>` on EC2 with no keys configured | Works (IAM role) |
| `/admin` without logging in | Redirects to the login page |
| Upload `notes.txt`, or a CSV with wrong columns | Rejected with a message |

## Load test
```powershell
pip install locust
locust -f loadtest/locustfile.py --host http://<elastic-ip> --headless -u 100 -r 10 -t 3m
```
CPU rises on the dashboard's System page and the CloudWatch dashboard. The CPU alarm fires within about 2 minutes and sends the SNS email.

## Scaling (optional extension)
The web tier is **stateless**: all data lives in S3 and RDS, so EC2 instances can be replaced or multiplied.
- **Vertical:** stop the instance, change its type, start it again.
- **Horizontal:**
  1. Create an AMI from the instance.
  2. Create a Launch Template from it.
  3. Create an Auto Scaling Group (min 1, max 2, target CPU 60%) behind an Application Load Balancer.
  4. Run the load test and watch a second instance launch.
  5. Remove the cron entries on the clones (`crontab -r -u ec2-user`), so only one instance runs the pipeline.

The load balancer isn't free, so create it only for the demo and delete it afterwards.

## Cost and teardown
Everything above fits the AWS free tier or student credits (about $0–5 a month). Public IPv4 addresses and RDS are the
main costs to watch. **AWS restarts a stopped RDS instance after 7 days.** After grading, delete in this order:
1. RDS (skip the final snapshot)
2. EC2 and release the Elastic IP
3. Empty and delete the S3 bucket
4. Alarms, the dashboard and log groups
5. SNS topic and SSM parameters

Then check the Billing page.
