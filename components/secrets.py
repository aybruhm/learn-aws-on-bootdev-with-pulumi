from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pulumi
import pulumi_aws as aws
from pulumi_aws.iam import GetPolicyDocumentStatementArgsDict

from config import EnvConfig


@dataclass
class SecretsOutputs:
    db_url_ssmparameter: aws.ssm.Parameter
    cmo_name_ssmparameter: aws.ssm.Parameter


def _construct_database_url(
    db_name: str,
    db_user: str,
    db_endpoint: str,
    db_password: str,
):
    url = f"postgresql://{db_user}:{db_password}@{db_endpoint}/{db_name}"
    return url


def make_ssm_parameters(
    name: str,
    data_plane_rds_instance: aws.rds.Instance,
    env: EnvConfig,
    tags: dict[str, Any],
) -> SecretsOutputs:
    # ====== Create parameters for database url
    param_name = f"{name}/database/url/{env.env_name}"
    db_url_ssmparameter = aws.ssm.Parameter(
        param_name,
        name="/DATABASE_URL",
        region=env.region,
        type=aws.ssm.ParameterType.SECURE_STRING,
        value=pulumi.Output.all(
            db_name=name,
            db_user=data_plane_rds_instance.username,
            db_endpoint=data_plane_rds_instance.endpoint,
            db_password=env.rds_master_password,
        ).apply(
            lambda vals: _construct_database_url(
                db_name=vals["db_name"],
                db_user=vals["db_user"],
                db_endpoint=vals["db_endpoint"],
                db_password=vals["db_password"],
            )
        ),
        tier="Standard",
        tags={**tags, "Name": param_name},
        opts=pulumi.ResourceOptions(
            depends_on=[data_plane_rds_instance],
        ),
    )

    # ====== Create parameters for cmo name
    param_name = f"{name}/cmo/name/{env.env_name}"
    cmo_name_ssmparameter = aws.ssm.Parameter(
        param_name,
        name="/CMO_NAME",
        region=env.region,
        type=aws.ssm.ParameterType.STRING,
        value=env.cmo_name,
        tier="Standard",
        tags={**tags, "Name": param_name},
    )

    return SecretsOutputs(
        db_url_ssmparameter=db_url_ssmparameter,
        cmo_name_ssmparameter=cmo_name_ssmparameter,
    )


def attach_ssm_parameters_to_ec2(
    name: str,
    ec2_role: aws.iam.Role,
    parameters: list[pulumi.Output[str]],
):
    # ===== Constructing IAM SSM Policy Document
    def _build_ssm_read_statements(
        names: Sequence[str],
    ) -> list[GetPolicyDocumentStatementArgsDict]:
        return [
            {
                "effect": "Allow",
                "actions": ["ssm:GetParameter", "ssm:GetParameters"],
                "resources": [f"arn:aws:ssm:*:*:parameter{name}" for name in names],
            }
        ]

    statements = pulumi.Output.all(*parameters).apply(_build_ssm_read_statements)
    iam_ec2_ssm_policy_document = aws.iam.get_policy_document_output(
        statements=statements
    )

    # ===== Create IAM SSM policy
    iam_ec2_ssm_policy = aws.iam.Policy(
        f"{name}-ssm-access",
        name=f"{name}-ssm",
        policy=iam_ec2_ssm_policy_document.json,
    )

    # Add policy to allow ec2 access to SSM parameters
    aws.iam.RolePolicyAttachment(
        f"{name}-ssm-params",
        policy_arn=iam_ec2_ssm_policy.arn,
        role=ec2_role.name,
    )
