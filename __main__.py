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

Ch 5-11. IAM, CloudWatch, Route 53, S3, CloudFront, ECS, Lambda
    Not yet implemented -- added as the course progresses.

Usage
-----
Prerequisites: AWS credentials in your environment and the Pulumi CLI.

1. Store your public IP (whitelists your machine for SSH in the security
   group; re-run whenever your IP changes):

       pulumi config set --secret local_ip "$(curl -s ifconfig.me)"

2. Store a master password for the RDS database:

       pulumi config set --secret rds_master_password "your-password"

3. Preview and deploy:

       pulumi preview
       pulumi up

4. Connect to the instance (the key is generated on the first deploy):

       ssh -i ~/.ssh/patientping-key ec2-user@$(pulumi stack output ec2_eip_public_ip)

5. Connect to the database from the instance (RDS only accepts connections
   from the EC2 security group):

       psql -h <endpoint-host> -U postgres -d patientping

   Get the endpoint from `pulumi stack output rds_instance_endpoint`.

6. Tear everything down:

       pulumi destroy

All resources and stack outputs are defined at the bottom of this module; inspect them with `pulumi stack output`.
"""

import pulumi

from components.backups import make_ec2_backup
from components.compute import make_compute
from components.data_plane import make_data_plane
from components.networking import make_networking
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

# Create compute
public_subnet_a = min(
    networking_outputs.public_subnets, key=lambda subnet: subnet._name
)
compute_outputs = make_compute(
    name=APP_NAME,
    vpc=networking_outputs.vpc,
    public_subnet=public_subnet_a,
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
