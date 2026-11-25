# Screenshots

**Already here** (captured from a local run on the real dataset, with "now" set to Monday 08:00 rush hour):
`overview.png`, `historical.png`, `prediction.png`, `map.png`, `model.png`, `system.png`.

**Still to capture once the app runs on AWS** (evidence for deliverable D4, see [../REQUIREMENTS.md](../REQUIREMENTS.md)):

1. `aws-overview.png`: the dashboard on the Elastic IP URL ("Running on AWS" shown top right)
2. `aws-system.png`: the System page with live CloudWatch charts
3. `s3-bucket.png`: the bucket with `raw/ processed/ models/ feed/`
4. `rds.png`: the RDS instance showing "Publicly accessible: No"
5. `security-groups.png`: the `traffic-rds-sg` inbound rule whose source is `traffic-ec2-sg`
6. `iam-role.png`: the EC2 role and its policies
7. `cloudwatch-dashboard.png` and `alarm-email.png` during the load test
8. `locust.png`: load-test results
9. `psql-timeout.png`: connecting to RDS from a laptop fails
10. `billing.png`: cost close to $0
