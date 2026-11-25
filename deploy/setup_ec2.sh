#!/bin/bash
# One-time server setup on a fresh Amazon Linux 2023 EC2 instance (t3.micro / t2.micro).
#
#   sudo dnf install -y git
#   sudo git clone https://github.com/<you>/<repo>.git /opt/traffic
#   cd /opt/traffic && sudo bash deploy/setup_ec2.sh      # run twice: 1st creates .env, 2nd installs
#
# Safe to re-run (e.g. after a git pull).
set -euo pipefail
APP_DIR=/opt/traffic
cd "$APP_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> Created $APP_DIR/.env - fill in S3_BUCKET, DB_HOST, RDS_INSTANCE_ID, then re-run this script."
  exit 0
fi
grep -q '^S3_BUCKET=.\+' .env && grep -q '^DB_HOST=.\+' .env || { echo ">>> Fill S3_BUCKET and DB_HOST in .env first"; exit 1; }

# 1. Swap: 1 GB RAM is tight for pip installs and model training
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

# 2. Packages
dnf install -y python3.11 python3.11-pip nginx amazon-cloudwatch-agent postgresql15 cronie
systemctl enable --now crond

# 3. Python environment
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# 4. Instance id for the dashboard's CloudWatch charts (IMDSv2)
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
sed -i "s/^EC2_INSTANCE_ID=.*/EC2_INSTANCE_ID=$IID/" .env

# 5. Logs + ownership (app runs as ec2-user, never root)
mkdir -p /var/log/traffic
chown -R ec2-user:ec2-user /var/log/traffic "$APP_DIR"

# 6. App service (gunicorn) + nginx reverse proxy
cp deploy/traffic-app.service /etc/systemd/system/traffic-app.service
cp deploy/nginx.conf /etc/nginx/nginx.conf
nginx -t
systemctl daemon-reload
systemctl enable traffic-app nginx
systemctl restart traffic-app nginx

# 7. Scheduled pipeline (hourly predict, nightly retrain)
crontab -u ec2-user deploy/crontab.txt

# 8. CloudWatch Agent: memory/disk metrics + app/nginx logs
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s \
  -c file:"$APP_DIR"/deploy/cloudwatch-agent.json

echo ">>> Done. Health check:"
sleep 3
curl -s http://127.0.0.1/health; echo
echo ">>> First data load (as ec2-user):"
echo "    cd $APP_DIR && sudo -u ec2-user .venv/bin/python -m pipeline.prepare_data && sudo -u ec2-user .venv/bin/python -m pipeline.run_all"
