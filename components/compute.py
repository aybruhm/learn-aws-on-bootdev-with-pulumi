import ipaddress
from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws

from config import EnvConfig


@dataclass
class ComputeOutputs:
    ec2_instance: aws.ec2.Instance
    key_pair: aws.ec2.KeyPair
    elastic_ip: aws.ec2.Eip
    public_sg: aws.ec2.SecurityGroup


def _generate_ssh_keys(
    key_name: str,
    path: str = "~/.ssh/patientping-key",
) -> str:
    import os
    import subprocess

    path = os.path.expanduser(path)

    # Idempotency: returns public key if path already exists
    if os.path.exists(f"{path}.pub"):
        try:
            with open(f"{path}.pub", mode="r") as file:
                return file.read()
        except OSError as exc:
            raise RuntimeError(
                f"Failed to read public key from {path}.pub: {exc}"
            ) from exc

    # Create new ssh key and return public key
    result = subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-C",
            key_name,
            "-f",
            path,
            "-N",
            "",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to generate SSH key for {key_name!r}: {result.stderr.strip()}"
        )

    try:
        with open(f"{path}.pub", mode="r") as file:
            return file.read()
    except OSError as exc:
        raise RuntimeError(f"Failed to read public key from {path}.pub: {exc}") from exc


def make_compute(
    name: str,
    vpc: aws.ec2.Vpc,
    public_subnet: aws.ec2.Subnet,
    ec2_instance_profile: aws.iam.InstanceProfile,
    env: EnvConfig,
    tags: dict[
        str,
        Any,
    ],
) -> ComputeOutputs:
    # ===== Generate SSH Key
    ssh_pub_key = _generate_ssh_keys(key_name=f"{name}-key")

    if "/" in env.local_ip:
        local_ip_network = ipaddress.ip_network(env.local_ip, strict=True)
    else:
        local_ip_network = ipaddress.ip_network(
            f"{env.local_ip}/{'128' if ':' in env.local_ip else '32'}",
            strict=True,
        )
    cidr_kwargs = (
        {"cidr_ipv6": str(local_ip_network)}
        if local_ip_network.version == 6
        else {"cidr_ipv4": str(local_ip_network)}
    )

    # ===== Import SSH Key into EC2
    key_name = f"{name}-key"
    kp = aws.ec2.KeyPair(
        key_name,
        key_name=key_name,
        public_key=ssh_pub_key,
        tags={**tags, "Name": key_name},
    )

    # ===== Create Security Group
    public_sg = aws.ec2.SecurityGroup(
        f"{name}-public-sg",
        name=f"{name}-public-sg",
        description="Allow public access to EC2",
        vpc_id=vpc.id,
        tags={**tags, "Name": f"{name}-public-sg"},
    )
    aws.vpc.SecurityGroupIngressRule(
        f"{name}-public-sg-ssh-ingress",
        description="Allow SSH from developer computer",
        from_port=22,
        to_port=22,
        ip_protocol="tcp",
        security_group_id=public_sg.id,
        tags={
            **tags,
            "Name": f"{name}-public-sg-ssh-ingress-rule",
        },
        **cidr_kwargs,  # type: ignore
    )
    aws.vpc.SecurityGroupIngressRule(
        f"{name}-public-sg-http-ingress",
        description="Allow web traffic for PatientPing site",
        from_port=8080,
        to_port=8080,
        ip_protocol="tcp",
        cidr_ipv4="0.0.0.0/0",
        security_group_id=public_sg.id,
        tags={
            **tags,
            "Name": f"{name}-public-sg-http-ingress-rule",
        },
    )
    aws.vpc.SecurityGroupEgressRule(
        f"{name}-public-sg-egress",
        description="Allow all outbound traffic",
        ip_protocol="-1",  # this allows all protocol (tcp, udp, etc),
        cidr_ipv4="0.0.0.0/0",
        security_group_id=public_sg.id,
        tags={
            **tags,
            "Name": f"{name}-public-sg-egress-rule",
        },
    )

    # ===== Create EC2 Instance
    ec2_instance = aws.ec2.Instance(
        f"{name}-web",
        ami="ami-002a966128d15711b",  # amazon-eks-node-al2023-x86_64-standard-1.30-v20260107 AMI
        instance_type=aws.ec2.InstanceType.T3_MICRO,
        key_name=kp.key_name,
        associate_public_ip_address=False,
        subnet_id=public_subnet.id,
        iam_instance_profile=ec2_instance_profile.name,
        security_groups=[public_sg.id],
        tags={**tags, "Name": f"{name}-web"},
        opts=pulumi.ResourceOptions(
            depends_on=[vpc],
            ignore_changes=["associate_public_ip_address"],
        ),
    )

    # ===== Create Elastic IP
    eip = aws.ec2.Eip(
        f"{name}-web-eip",
        instance=ec2_instance.id,
        domain="vpc",
        tags={**tags, "Name": f"{name}-web-eip"},
    )
    aws.ec2.EipAssociation(
        f"{name}-web-eip-association",
        allocation_id=eip.id,
        instance_id=ec2_instance.id,
    )

    return ComputeOutputs(
        key_pair=kp,
        ec2_instance=ec2_instance,
        elastic_ip=eip,
        public_sg=public_sg,
    )
