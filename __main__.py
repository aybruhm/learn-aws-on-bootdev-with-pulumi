"""An AWS Python Pulumi program"""

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
