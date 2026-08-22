from dataclasses import dataclass

import pulumi


@dataclass
class EnvConfig:
    env_name: str
    local_ip: pulumi.Output[str]


def load_env_config() -> EnvConfig:
    config = pulumi.Config()
    stack = pulumi.get_stack()
    env_config = EnvConfig(
        env_name=stack,
        local_ip=config.require_secret("local_ip"),
    )
    return env_config
