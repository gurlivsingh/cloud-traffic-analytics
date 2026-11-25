#!/bin/bash
# Creates the CloudWatch side of the project. Run once in AWS CloudShell (region ap-south-1):
#
#   bash create_monitoring.sh you@example.com i-0123456789abcdef0 traffic-db
#
# -> SNS topic + email subscription (confirm the email!), 3 alarms, a CloudWatch dashboard,
#    and 7-day retention on the app's log groups.
set -euo pipefail
EMAIL="${1:?usage: bash create_monitoring.sh EMAIL EC2_INSTANCE_ID [RDS_INSTANCE_ID]}"
IID="${2:?EC2 instance id missing}"
DB="${3:-traffic-db}"
export AWS_DEFAULT_REGION=ap-south-1

TOPIC=$(aws sns create-topic --name traffic-alerts --query TopicArn --output text)
aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$EMAIL" >/dev/null
echo "SNS topic $TOPIC - check $EMAIL and click 'Confirm subscription'"

# CPU from the CloudWatch Agent (60 s resolution, so the alarm fires within ~2 min of a load test)
aws cloudwatch put-metric-alarm --alarm-name traffic-ec2-cpu-high \
  --alarm-description "EC2 CPU above 70% for 2 minutes" \
  --namespace CWAgent --metric-name cpu_usage_active --dimensions Name=InstanceId,Value="$IID" \
  --statistic Average --period 60 --evaluation-periods 2 --threshold 70 \
  --comparison-operator GreaterThanThreshold --alarm-actions "$TOPIC" --ok-actions "$TOPIC"

aws cloudwatch put-metric-alarm --alarm-name traffic-rds-low-storage \
  --alarm-description "RDS free storage below 2 GB" \
  --namespace AWS/RDS --metric-name FreeStorageSpace --dimensions Name=DBInstanceIdentifier,Value="$DB" \
  --statistic Minimum --period 300 --evaluation-periods 1 --threshold 2000000000 \
  --comparison-operator LessThanThreshold --alarm-actions "$TOPIC"

aws cloudwatch put-metric-alarm --alarm-name traffic-pipeline-failed \
  --alarm-description "An ETL run failed (see /traffic/pipeline logs)" \
  --namespace TrafficAnalytics --metric-name PipelineFailures \
  --statistic Sum --period 300 --evaluation-periods 1 --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching \
  --alarm-actions "$TOPIC"

for g in /traffic/app /traffic/access /traffic/pipeline /traffic/nginx; do
  aws logs create-log-group --log-group-name "$g" 2>/dev/null || true
  aws logs put-retention-policy --log-group-name "$g" --retention-in-days 7
done

R=ap-south-1
aws cloudwatch put-dashboard --dashboard-name TrafficAnalytics --dashboard-body "$(cat <<EOF
{"widgets":[
 {"type":"metric","x":0,"y":0,"width":12,"height":6,"properties":{"title":"EC2 CPU %","region":"$R","stat":"Average","period":60,
  "metrics":[["CWAgent","cpu_usage_active","InstanceId","$IID"],["AWS/EC2","CPUUtilization","InstanceId","$IID"]]}},
 {"type":"metric","x":12,"y":0,"width":12,"height":6,"properties":{"title":"EC2 memory / disk %","region":"$R","stat":"Average","period":60,
  "metrics":[["CWAgent","mem_used_percent","InstanceId","$IID"],["CWAgent","disk_used_percent","InstanceId","$IID"]]}},
 {"type":"metric","x":0,"y":6,"width":12,"height":6,"properties":{"title":"RDS CPU % and connections","region":"$R","stat":"Average","period":300,
  "metrics":[["AWS/RDS","CPUUtilization","DBInstanceIdentifier","$DB"],["AWS/RDS","DatabaseConnections","DBInstanceIdentifier","$DB",{"yAxis":"right"}]]}},
 {"type":"metric","x":12,"y":6,"width":12,"height":6,"properties":{"title":"Pipeline","region":"$R","stat":"Sum","period":300,
  "metrics":[["TrafficAnalytics","RowsLoaded"],["TrafficAnalytics","PipelineDurationSec",{"stat":"Maximum","yAxis":"right"}],["TrafficAnalytics","PipelineFailures"]]}},
 {"type":"alarm","x":0,"y":12,"width":24,"height":3,"properties":{"title":"Alarms","alarms":[
  "arn:aws:cloudwatch:$R:$(aws sts get-caller-identity --query Account --output text):alarm:traffic-ec2-cpu-high",
  "arn:aws:cloudwatch:$R:$(aws sts get-caller-identity --query Account --output text):alarm:traffic-rds-low-storage",
  "arn:aws:cloudwatch:$R:$(aws sts get-caller-identity --query Account --output text):alarm:traffic-pipeline-failed"]}}
]}
EOF
)" >/dev/null
echo "Done: 3 alarms + dashboard 'TrafficAnalytics' created."
