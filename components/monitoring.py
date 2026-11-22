from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws

from config import EnvConfig


@dataclass
class ExternalMonitoringOutputs:
    cw_dashboard: aws.cloudwatch.Dashboard


@dataclass
class InternalMonitoringOutputs:
    monitoring_role: aws.iam.Role
    logs_access_policy: aws.iam.Policy
    ssm_access_policy: aws.iam.Policy
    ec2_monitoring_profile: aws.iam.InstanceProfile


@dataclass
class MonitoringAlarmOutputs:
    cw_sns_topic: aws.sns.Topic
    cw_alarm: aws.cloudwatch.MetricAlarm
    cw_sns_subscription: aws.sns.TopicSubscription


def make_external_monitoring(
    name: str,
    ec2_instance: aws.ec2.Instance,
    env: EnvConfig,
    tags: dict[str, Any],
) -> ExternalMonitoringOutputs:
    # ====== Create external monitoring resources
    cw_dashboard = aws.cloudwatch.Dashboard(
        f"{name}-dashboard",
        dashboard_name=f"{name}-dashboard",
        dashboard_body=pulumi.Output.json_dumps(
            {
                "start": "-PT15M",
                "widgets": [
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 0,
                        "width": 12,
                        "height": 6,
                        "properties": {
                            "view": "timeSeries",
                            "stacked": False,
                            "metrics": [
                                [
                                    "AWS/EC2",
                                    "CPUUtilization",
                                    "InstanceId",
                                    ec2_instance.id,
                                ]
                            ],
                            "period": 60,
                            "stat": "Maximum",
                            "region": ec2_instance.region,
                            "title": f"{name} CPU",
                        },
                    }
                ],
            }
        ),
    )

    return ExternalMonitoringOutputs(cw_dashboard=cw_dashboard)


def make_internal_monitoring(
    name: str,
    ec2_instance: aws.ec2.Instance,
    env: EnvConfig,
    tags: dict[str, Any],
) -> InternalMonitoringOutputs:
    # ====== Create IAM role for CloudWatch agent
    pp_monitoring_role = aws.iam.Role(
        f"{name}-monitoring-role",
        assume_role_policy=pulumi.Output.json_dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Effect": "Allow",
                        "Sid": "",
                    }
                ],
            }
        ),
        opts=pulumi.ResourceOptions(
            depends_on=[ec2_instance],
        ),
        tags={**tags, "Name": f"{name}-monitoring-role"},
    )

    # ====== Create IAM policy for CloudWatch (logs access)
    pp_monitoring_policy = aws.iam.Policy(
        f"{name}-cloudwatch-logs-access",
        policy=pulumi.Output.json_dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                            "logs:DescribeLogStreams",
                        ],
                        "Resource": ["arn:aws:logs:*:*:*"],
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["cloudwatch:PutMetricData", "ec2:DescribeTags"],
                        "Resource": "*",
                    },
                ],
            }
        ),
        tags={**tags, "Name": f"{name}-cloudwatch-logs-access"},
    )

    # ====== Create IAM policy for CloudWatch (SSM access)
    pp_ssm_policy = aws.iam.Policy(
        f"{name}-cloudwatch-ssm-access",
        policy=pulumi.Output.json_dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ssm:GetParameter", "ssm:GetParameters"],
                        "Resource": [
                            "arn:aws:ssm:*:*:parameter/DATABASE_URL",
                            "arn:aws:ssm:*:*:parameter/CMO_NAME",
                        ],
                    }
                ],
            }
        ),
        tags={**tags, "Name": f"{name}-cloudwatch-cmo-access"},
    )

    # ====== Attach policies to role
    aws.iam.RolePolicyAttachment(
        f"{name}-monitoring-role-policy-attachment",
        role=pp_monitoring_role.name,
        policy_arn=pp_monitoring_policy.arn,
    )
    aws.iam.RolePolicyAttachment(
        f"{name}-ssm-role-policy-attachment",
        role=pp_monitoring_role.name,
        policy_arn=pp_ssm_policy.arn,
    )

    # ====== Update ec2 instance IAM role to include monitoring role
    ec2_monitoring_profile = aws.iam.InstanceProfile(
        f"{name}-instance-profile",
        name=f"{name}-instance-profile",
        role=pp_monitoring_role.name,
        tags={**tags, "Name": f"{name}-instance-profile"},
    )
    return InternalMonitoringOutputs(
        monitoring_role=pp_monitoring_role,
        logs_access_policy=pp_monitoring_policy,
        ssm_access_policy=pp_ssm_policy,
        ec2_monitoring_profile=ec2_monitoring_profile,
    )


def make_monitoring_alarm(
    name: str,
    ec2_instance: aws.ec2.Instance,
    env: EnvConfig,
    tags: dict[str, Any],
) -> MonitoringAlarmOutputs:
    # ===== Create SNS topic for alarm notifications
    cw_sns_topic = aws.sns.Topic(
        f"{name}-alerts",
        name=f"{name}-alerts",
        display_name=f"{name}-alerts",
        tags={**tags, "Name": f"{name}-cpu-alerts"},
    )

    # ===== Create SNS subscription for alarm notifications
    cw_sns_topic_subscription = aws.sns.TopicSubscription(
        f"{name}-alerts-subscription",
        topic=cw_sns_topic.arn,
        protocol="email",
        endpoint=env.alert_email,
    )

    # ====== Create CloudWatch alarm for EC2 instance
    cw_alarm = aws.cloudwatch.MetricAlarm(
        f"{name}-cpu-alarm",
        name=f"{name}-cpu-alarm",
        alarm_description="Alert when CPU exceeds 20%",
        comparison_operator="GreaterThanThreshold",
        evaluation_periods=1,
        metric_name="CPUUtilization",
        namespace="AWS/EC2",
        period=60 * 5,  # 5 minutes
        statistic="Average",
        alarm_actions=[cw_sns_topic.arn],
        ok_actions=[cw_sns_topic.arn],
        threshold=20,
        dimensions={"InstanceId": ec2_instance.id},
        tags={**tags, "Name": f"{name}-cpu-alarm"},
    )

    return MonitoringAlarmOutputs(
        cw_sns_topic=cw_sns_topic,
        cw_alarm=cw_alarm,
        cw_sns_subscription=cw_sns_topic_subscription,
    )
