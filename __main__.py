"""PatientPing: real AWS infrastructure built alongside the Boot.dev AWS course.

Each chapter of the course introduces a new AWS service; this program provisions the corresponding resources with Pulumi, chapter by chapter.

Architecture (by course chapter)
--------------------------------
Ch 1. Cloud Computing
    Core concepts only -- nothing provisioned.

Ch 2. Networking -- VPCs
    - VPC (10.0.0.0/22) in eu-west-2
    - 2 public subnets (eu-west-2a/b) and 2 private subnets (eu-west-2c/d)
    - Internet gateway
    - Public and private route tables with subnet associations

Ch 3. EC2 -- Elastic Compute Cloud
    - Security group: SSH from your IP, unrestricted egress
    - t3.micro Amazon Linux 2023 instance in a public subnet
    - SSH key pair (generated at ~/.ssh/patientping-key on first deploy)
    - Elastic IP for a stable public address
    - AMI snapshot and launch template of the web instance
    - Backup instance (patientping-web-v2) built from the launch template

Ch 4. RDS -- Relational Database Service
    - Private subnet group spanning the private subnets
    - RDS security group: Postgres (5432) from the EC2 security group only
    - Primary Postgres instance (patientping-db) in eu-west-2c
      (t3.micro, 20 GB encrypted gp2 storage, latest engine version)
    - Read replica (patientping-replica)

Ch 5. IAM -- Identity and Access Management
    - IAM user (patientping-admin-vinny)
    - Managed policy (patientping-ec2-readonly): ec2:Describe* on all
      resources
    - IAM group (patientping-ec2-readers) with the policy attached, and
      the user added to the group via a user-group membership
    - IAM role (patientping-ec2-readonly-role) trusted by the EC2 service,
      with the policy attached, exposed to EC2 through an instance profile
      on the web instance
    - SSM parameters:
      * /DATABASE_URL (SecureString): Postgres connection string built
        from the RDS endpoint, master password, and database name
      * /CMO_NAME (String): the CMO name from stack config
    - IAM policy (patientping-ssm-access) granting ssm:GetParameter /
      ssm:GetParameters on both parameters, attached to the EC2 role

Ch 6-11. CloudWatch, Route 53, S3, CloudFront, ECS, Lambda
    Not yet implemented -- added as the course progresses.
"""

import pulumi

from components.backups import make_ec2_backup
from components.compute import make_compute
from components.data_plane import make_data_plane
from components.iam import make_iam
from components.networking import make_networking
from components.secrets import attach_ssm_parameters_to_ec2, make_ssm_parameters
from components.snapshots import make_snapshots
from config import load_env_config

# Constants
APP_NAME = "patientping"
DEFAULT_TAGS = {
    "Name": APP_NAME,
    "ManagedBy": "Pulumi",
}
AVAILABILITY_ZONES = {
    "public": ["eu-west-2a", "eu-west-2b"],
    "private": ["eu-west-2c", "eu-west-2d"],
}

# Initialize env config
env_config = load_env_config()

# Create Networking
networking_outputs = make_networking(
    name=APP_NAME,
    tags=DEFAULT_TAGS,
    availability_zones=AVAILABILITY_ZONES,
)

# Create IAM
iam_outputs = make_iam(
    name=APP_NAME,
    env=env_config,
    tags=DEFAULT_TAGS,
)

# Create compute
public_subnet_a = min(
    networking_outputs.public_subnets,
    key=lambda subnet: subnet._name,
)
compute_outputs = make_compute(
    name=APP_NAME,
    vpc=networking_outputs.vpc,
    public_subnet=public_subnet_a,
    ec2_instance_profile=iam_outputs.ec2_instance_profile,
    env=env_config,
    tags=DEFAULT_TAGS,
)

# Create snapshots
snapshot_outputs = make_snapshots(
    name=APP_NAME,
    ec2_instance=compute_outputs.ec2_instance,
    key_pair=compute_outputs.key_pair,
    public_subnet=public_subnet_a,
    public_security_group=compute_outputs.public_sg,
    env=env_config,
    tags=DEFAULT_TAGS,
)

# Create backups
# -------- ec2
ec2_backup_outputs = make_ec2_backup(
    name=APP_NAME,
    ec2_launch_template=snapshot_outputs.ec2_launch_template,
    ec2_eip=compute_outputs.elastic_ip,
    env=env_config,
    tags=DEFAULT_TAGS,
)

# Create data plane
eu_west_2c = AVAILABILITY_ZONES["private"][0]
data_plane_bundle = make_data_plane(
    name=APP_NAME,
    vpc=networking_outputs.vpc,
    availability_zone=eu_west_2c,
    ec2_public_sg=compute_outputs.public_sg,
    private_subnets=networking_outputs.private_subnets,
    env=env_config,
    tags=DEFAULT_TAGS,
)

# Create ssm parameters
ssm_parameters_outputs = make_ssm_parameters(
    name=APP_NAME,
    data_plane_rds_instance=data_plane_bundle.rds_instance,
    env=env_config,
    tags=DEFAULT_TAGS,
)
attach_ssm_parameters_to_ec2(
    name=APP_NAME,
    ec2_role=iam_outputs.ec2_role,
    parameters=[
        ssm_parameters_outputs.cmo_name_ssmparameter.name,
        ssm_parameters_outputs.db_url_ssmparameter.name,
    ],
)


# Export resources output
pulumi.export("vpc_id", networking_outputs.vpc.id)
pulumi.export(
    "vpc_subnets",
    {
        subnet._name: {
            "id": subnet.id,
            "availability_zone": subnet.availability_zone,
            "cidr_block": subnet.cidr_block,
        }
        for subnet in (
            networking_outputs.private_subnets + networking_outputs.public_subnets
        )
    },
)
pulumi.export("vpc_igw", networking_outputs.internet_gateway.id)
pulumi.export("vpc_public_rt", networking_outputs.public_rt.id)
pulumi.export("ec2_id", compute_outputs.ec2_instance.id)
pulumi.export("ec2_public_sg_id", compute_outputs.public_sg.id)
pulumi.export("ec2_keypair", compute_outputs.key_pair.key_name)
pulumi.export("ec2_eip_name", compute_outputs.elastic_ip._name)
pulumi.export("ec2_eip_public_ip", compute_outputs.elastic_ip.public_ip)
pulumi.export("ec2_ami_id", snapshot_outputs.ec2_ami.id)
pulumi.export("ec2_launch_template_id", snapshot_outputs.ec2_launch_template.id)
pulumi.export("ec2_backup_id", ec2_backup_outputs.ec2_instance.id)
pulumi.export("rds_instance_endpoint", data_plane_bundle.rds_instance.endpoint)
pulumi.export(
    "rds_replica_instance_endpoint", data_plane_bundle.rds_replica_instance.endpoint
)
pulumi.export("iam_user_id", iam_outputs.user.id)
pulumi.export("iam_policy_id", iam_outputs.policy.id)
pulumi.export("iam_group_id", iam_outputs.group.id)
pulumi.export(
    "iam_user_group_membership",
    {
        "id": iam_outputs.user_group_membership.id,
        "groups": iam_outputs.user_group_membership.groups,
        "user": iam_outputs.user_group_membership.user,
    },
)
pulumi.export(
    "db_url_ssm_parameter_id",
    ssm_parameters_outputs.db_url_ssmparameter.id,
)
pulumi.export(
    "cmo_name_ssm_parameter_id",
    ssm_parameters_outputs.cmo_name_ssmparameter.id,
)
