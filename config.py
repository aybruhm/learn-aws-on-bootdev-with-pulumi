from dataclasses import dataclass


@dataclass
class EnvConfig:
    env_name: str


def load_env_config() -> EnvConfig:
    import pulumi

    stack = pulumi.get_stack()
    env_config = EnvConfig(
        env_name=stack,
    )
    return env_config
