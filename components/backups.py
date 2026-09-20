from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws

from config import EnvConfig


@dataclass
class EC2BackupOutputs:
    ec2_instance: aws.ec2.Instance


def make_ec2_backup(
    name: str,
    ec2_launch_template: aws.ec2.LaunchTemplate,
    ec2_eip: aws.ec2.Eip,
    env: EnvConfig,
    tags: dict[str, Any],
) -> EC2BackupOutputs:
    # Create EC2 Backup from Launch Template
    ec2_instance = aws.ec2.Instance(
        f"{name}-web-v2",
        launch_template=aws.ec2.InstanceLaunchTemplateArgs(
            id=ec2_launch_template.id,
        ),
        tags={**tags, "Name": f"{name}-web-v2"},
        opts=pulumi.ResourceOptions(
            depends_on=[ec2_launch_template, ec2_eip],
        ),
        
    )

    # Add EC2 Backup to EIP
    aws.ec2.EipAssociation(
        f"{name}-web-v2-eip-association",
        allocation_id=ec2_eip.id,
        instance_id=ec2_instance.id,
    )
    return EC2BackupOutputs(ec2_instance=ec2_instance)
