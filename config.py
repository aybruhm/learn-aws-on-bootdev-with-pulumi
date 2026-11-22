from dataclasses import dataclass

import pulumi
import pulumi_aws as aws


@dataclass
class EnvConfig:
    region: str
    env_name: str
    local_ip: str
    rds_master_password: pulumi.Output[str]
    alert_email: pulumi.Output[str]
    cmo_name: str


def load_env_config() -> EnvConfig:
    config = pulumi.Config()
    stack = pulumi.get_stack()
    current_region = aws.get_region()
    env_config = EnvConfig(
        region=current_region.region,
        env_name=stack,
        local_ip=config.require("local_ip"),
        rds_master_password=config.require_secret("rds_master_password"),
        alert_email=config.require_secret("alert_email"),
        cmo_name=config.require("cmo_name"),
    )
    return env_config
