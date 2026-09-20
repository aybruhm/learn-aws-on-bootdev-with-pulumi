from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws

from config import EnvConfig


@dataclass
class SnapshotOutputs:
    ec2_ami: aws.ec2.AmiFromInstance
    ec2_launch_template: aws.ec2.LaunchTemplate


def make_snapshots(
    name: str,
    ec2_instance: aws.ec2.Instance,
    key_pair: aws.ec2.KeyPair,
    public_subnet: aws.ec2.Subnet,
    public_security_group: aws.ec2.SecurityGroup,
    env: EnvConfig,
    tags: dict[str, Any],
) -> SnapshotOutputs:
    # ===== Create EC2 AMI
    ami_name = f"{name}-web-ami"
    ec2_ami = aws.ec2.AmiFromInstance(
        ami_name,
        name=ami_name,
        description="AMI for web server",
        source_instance_id=ec2_instance.id,
        snapshot_without_reboot=False,
        tags={
            **tags,
            "Name": ami_name,
        },
        opts=pulumi.ResourceOptions(
            depends_on=[ec2_instance],
        ),
    )

    # ===== Create EC2 Launch Template
    launch_template_name = f"{name}-web-launcher"
    ec2_launch_template = aws.ec2.LaunchTemplate(
        launch_template_name,
        name=launch_template_name,
        description="Launch template for t3.micro with PatientPing app preinstalled",
        image_id=ec2_ami.id,
        instance_type=aws.ec2.InstanceType.T3_MICRO,
        key_name=key_pair.key_name,
        network_interfaces=[
            {
                "security_groups": [public_security_group.id],
                "subnet_id": public_subnet.id,
            }
        ],
        block_device_mappings=[
            aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
                device_name="/dev/xvda",
                ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
                    delete_on_termination="true",
                    volume_size=8,
                    volume_type="gp3",
                ),
            ),
        ],
        tags={
            **tags,
            "Name": launch_template_name,
        },
        opts=pulumi.ResourceOptions(
            depends_on=[ec2_ami, key_pair],
        ),
    )

    return SnapshotOutputs(
        ec2_ami=ec2_ami,
        ec2_launch_template=ec2_launch_template,
    )
