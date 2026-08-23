from dataclasses import dataclass
from typing import Any

import pulumi_aws as aws


@dataclass
class NetworkingOutputs:
    vpc: aws.ec2.Vpc
    private_subnets: list[aws.ec2.Subnet]
    public_subnets: list[aws.ec2.Subnet]
    internet_gateway: aws.ec2.InternetGateway
    public_rt: aws.ec2.RouteTable


def make_networking(
    name: str,
    availability_zones: dict[str, list[str]],
    tags: dict[str, Any],
) -> NetworkingOutputs:
    # ===== Create vpc
    vpc = aws.ec2.Vpc(
        name,
        tags=tags,
        cidr_block="10.0.0.0/22",
    )

    # ===== Create subnets
    cidr_index = 0
    subnets: list[aws.ec2.Subnet] = []
    for zone_name, zones in availability_zones.items():
        for index, availability_zone in enumerate(zones, start=1):
            subnet_name = f"{name}-{zone_name}-{index}"
            subnet = aws.ec2.Subnet(
                subnet_name,
                availability_zone=availability_zone,
                cidr_block=f"10.0.{cidr_index}.0/24",
                vpc_id=vpc.id,
                tags={**tags, "Name": f"{name}-{zone_name}-{index}"},
            )
            subnets.append(subnet)
            cidr_index += 1

    # ===== Create internet gateway
    igw = aws.ec2.InternetGateway(
        f"{name}-igw",
        vpc_id=vpc.id,
        tags={**tags, "Name": f"{name}-igw"},
    )

    # ===== Create route table
    # ----- Public
    public_rt = aws.ec2.RouteTable(
        f"{name}-public-rtb",
        vpc_id=vpc.id,
        routes=[
            aws.ec2.RouteTableRouteArgs(
                cidr_block="0.0.0.0/0",
                gateway_id=igw.id,
            )
        ],
        tags={**tags, "Name": f"{name}-public-rtb"},
    )

    # ----- Public
    private_rt = aws.ec2.RouteTable(
        f"{name}-private-rtb",
        vpc_id=vpc.id,
        tags={**tags, "Name": f"{name}-private-rtb"},
    )

    # ===== Create route table association for public subnets
    public_subnets = [subnet for subnet in subnets if "public" in subnet._name]
    for index, subnet in enumerate(public_subnets):
        aws.ec2.RouteTableAssociation(
            f"{name}-rtb-association-public-{index + 1}",
            subnet_id=subnet.id,
            route_table_id=public_rt.id,
        )

    # ===== Create route table association for private subnets
    private_subnets = [subnet for subnet in subnets if "private" in subnet._name]
    for index, subnet in enumerate(private_subnets):
        aws.ec2.RouteTableAssociation(
            f"{name}-rtb-association-private-{index + 1}",
            subnet_id=subnet.id,
            route_table_id=private_rt.id,
        )

    return NetworkingOutputs(
        vpc=vpc,
        public_subnets=public_subnets,
        private_subnets=private_subnets,
        internet_gateway=igw,
        public_rt=public_rt,
    )
