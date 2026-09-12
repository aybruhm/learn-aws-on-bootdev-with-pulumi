import json
from dataclasses import dataclass
from typing import Any

import pulumi_aws as aws

from config import EnvConfig


@dataclass
class IAMOutputs:
    user: aws.iam.User
    policy: aws.iam.Policy
    group: aws.iam.Group
    ec2_role: aws.iam.Role
    ec2_instance_profile: aws.iam.InstanceProfile
    user_group_membership: aws.iam.UserGroupMembership


def make_iam(
    name: str,
    env: EnvConfig,
    tags: dict[str, Any],
) -> IAMOutputs:
    # ===== Create IAM user
    iam_user_name = f"{name}-admin-vinny"
    iam_user = aws.iam.User(
        iam_user_name,
        name=iam_user_name,
        tags={**tags, "Name": iam_user_name},
    )

    # ===== Constructing IAM EC2 Policy Document
    iam_ec2_policy_document = aws.iam.get_policy_document(
        statements=[
            {
                "effect": "Allow",
                "actions": ["ec2:Describe*"],
                "resources": ["*"],
            }
        ]
    )

    # ===== Create IAM policy
    iam_ec2_policy = aws.iam.Policy(
        f"{name}-ec2-readonly",
        name=f"{name}-ec2-readonly",
        policy=iam_ec2_policy_document.json,
    )

    # ===== Create Deny All Policy for IAM User
    iam_deny_all_policy_document = aws.iam.get_policy_document(
        statements=[
            {
                "sid": "DenyEverything",
                "effect": "Deny",
                "actions": ["*"],
                "resources": ["*"],
            }
        ]
    )
    iam_deny_all_policy = aws.iam.Policy(
        f"{name}-deny-all",
        name=f"{name}-deny-all",
        description="Denies all actions for the IAM user.",
        policy=iam_deny_all_policy_document.json,
    )

    # ===== Create IAM role
    iam_ec2_role_name = f"{name}-ec2-readonly-role"
    iam_ec2_role = aws.iam.Role(
        iam_ec2_role_name,
        name=iam_ec2_role_name,
        description="Allows EC2 instances to call AWS services on your behalf.",
        force_detach_policies=True,
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "ec2.amazonaws.com",
                        },
                    }
                ],
            }
        ),
    )
    aws.iam.RolePolicyAttachment(
        f"{iam_ec2_role_name}-ply-attmnt",
        policy_arn=iam_ec2_policy.arn,
        role=iam_ec2_role.name,
    )
    aws.iam.RolePolicyAttachment(
        f"{iam_ec2_role_name}-deny-all-ply-attmnt",
        policy_arn=iam_deny_all_policy.arn,
        role=iam_ec2_role.name,
    )

    # ===== Create IAM instance profile
    iam_ec2_instance_profile = aws.iam.InstanceProfile(
        f"{iam_ec2_role_name}-instance-profile",
        name=f"{iam_ec2_role_name}-instance-profile",
        role=iam_ec2_role.name,
    )

    # ===== Create IAM group, group policy
    # and add user to group
    iam_group = aws.iam.Group(
        f"{name}-ec2-readers",
        name=f"{name}-ec2-readers",
    )
    aws.iam.GroupPolicyAttachment(
        f"{name}-ec2-readonly",
        group=iam_group.name,
        policy_arn=iam_ec2_policy.arn,
    )
    iam_group_membership = aws.iam.UserGroupMembership(
        f"{name}-ec2-readers",
        groups=[iam_group.name],
        user=iam_user.name,
    )

    return IAMOutputs(
        user=iam_user,
        policy=iam_ec2_policy,
        group=iam_group,
        ec2_role=iam_ec2_role,
        ec2_instance_profile=iam_ec2_instance_profile,
        user_group_membership=iam_group_membership,
    )
