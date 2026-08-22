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

Ch 4-11. RDS, IAM, CloudWatch, Route 53, S3, CloudFront, ECS, Lambda
    ...

Usage
-----
Prerequisites: AWS credentials in your environment and the Pulumi CLI.

1. Store your public IP (whitelists your machine for SSH in the security
   group; re-run whenever your IP changes):

       pulumi config set --secret local_ip "$(curl -s ifconfig.me)"

2. Preview and deploy:

       pulumi preview
       pulumi up

3. Connect to the instance (the key is generated on the first deploy):

       ssh -i ~/.ssh/patientping-key ec2-user@$(pulumi stack output ec2_eip_public_ip)

4. Tear everything down:

       pulumi destroy

All resources and stack outputs are defined at the bottom of this module; inspect them with `pulumi stack output`.
"""

import pulumi

from components.compute import make_compute
from components.networking import make_networking
from config import load_env_config

# Constants
APP_NAME = "patientping"
DEFAULT_TAGS = {
    "Name": APP_NAME,
    "ManagedBy": "Pulumi",
}

# Initialize env config
env_config = load_env_config()

# Create Networking
networking_outputs = make_networking(
    name=APP_NAME,
    tags=DEFAULT_TAGS,
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

# Export the name of the bucket
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
pulumi.export("ec2_dns", compute_outputs.ec2_instance.public_dns)
pulumi.export("ec2_keypair", compute_outputs.key_pair.key_name)
pulumi.export("ec2_eip_name", compute_outputs.elastic_ip._name)
pulumi.export("ec2_eip_public_ip", compute_outputs.elastic_ip.public_ip)
