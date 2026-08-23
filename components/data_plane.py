from dataclasses import dataclass
from typing import Any

import pulumi_aws as aws

from config import EnvConfig


@dataclass
class DataPlaneBundle:
    rds_instance: aws.rds.Instance
    rds_replica_instance: aws.rds.Instance
    rds_sg: aws.ec2.SecurityGroup


def make_data_plane(
    name: str,
    vpc: aws.ec2.Vpc,
    availability_zone: str,
    ec2_public_sg: aws.ec2.SecurityGroup,
    private_subnets: list[aws.ec2.Subnet],
    env: EnvConfig,
    tags: dict[
        str,
        Any,
    ],
) -> DataPlaneBundle:
    # ===== Create RDS Subnet Group
    rds_private_sg_name = f"{name}-private-subnet-group"
    rds_private_subnet_group = aws.rds.SubnetGroup(
        rds_private_sg_name,
        name=rds_private_sg_name,
        description="Private subnets for RDS DB instances",
        subnet_ids=[subnet.id for subnet in private_subnets],
        tags={**tags, "Name": rds_private_sg_name},
    )

    # ===== Create RDS VPC Security Group
    rds_security_group_name = f"{name}-rds-sg"
    rds_security_group = aws.ec2.SecurityGroup(
        rds_security_group_name,
        name=rds_security_group_name,
        description="Allow ec2 access to RDS",
        vpc_id=vpc.id,
        tags={**tags, "Name": rds_security_group_name},
    )
    aws.vpc.SecurityGroupIngressRule(
        f"{rds_security_group_name}-postgres-ingress",
        description="Allow inbound traff to Postgres from resources",
        from_port=5432,
        to_port=5432,
        ip_protocol="tcp",
        referenced_security_group_id=ec2_public_sg.id,
        security_group_id=rds_security_group.id,
        tags={
            **tags,
            "Name": f"{name}-postgres-ingress-rule",
        },
    )

    # ===== Create Postgres RDS
    rds_instance_name = f"{name}-db"
    engine_version_result = aws.rds.get_engine_version(
        engine=aws.rds.EngineType.POSTGRES,
        latest=True,
    )
    rds_instance = aws.rds.Instance(
        rds_instance_name,
        identifier=rds_instance_name,
        engine=aws.rds.EngineType.POSTGRES,
        # settings
        engine_version=engine_version_result.version,
        username="postgres",
        password=env.rds_master_password,
        iam_database_authentication_enabled=False,
        # connectivity
        db_subnet_group_name=rds_private_subnet_group.name,
        availability_zone=availability_zone,
        vpc_security_group_ids=[rds_security_group.id],
        # instance configuration
        instance_class=aws.rds.InstanceType.T3_MICRO,
        # storage
        allocated_storage=20,
        storage_encrypted=True,
        storage_type="gp2",
        # monitoring
        database_insights_mode="standard",
        performance_insights_enabled=False,
        # additional
        db_name=name,
        backup_retention_period=1,
        copy_tags_to_snapshot=True,
        tags={**tags, "Name": rds_instance_name},
    )

    # ===== Create Postgres RDS Replica
    rds_replica_instance_name = f"{name}-replica"
    rds_replica_instance = aws.rds.Instance(
        rds_replica_instance_name,
        identifier=rds_replica_instance_name,
        # instance configuration
        instance_class=rds_instance.instance_class,
        # settings
        replicate_source_db=rds_instance.identifier,
        # connectivity
        vpc_security_group_ids=[rds_security_group.id],
        # monitoring
        database_insights_mode="standard",
        performance_insights_enabled=False,
        # additional
        skip_final_snapshot=True,
        tags={**tags, "Name": rds_replica_instance_name},
    )
    return DataPlaneBundle(
        rds_instance=rds_instance,
        rds_replica_instance=rds_replica_instance,
        rds_sg=rds_security_group,
    )
