# PatientPing — the Boot.dev AWS course, rebuilt with Pulumi

Real AWS infrastructure, provisioned chapter by chapter while retaking the Boot.dev AWS course with [Pulumi](https://www.pulumi.com/) as the infrastructure-as-code tool instead of the AWS console (ClickOps).

## Why this project exists

I originally completed the Boot.dev AWS course in April 2026. This repository is a second pass through the same material with one twist: every resource is defined in Python and deployed with Pulumi. The goal is to revisit the AWS
services themselves while making use of Pulumi IaC.

## Architecture, chapter by chapter

| Chapter | Topic | Resources |
|---|---|---|
| 1 | Cloud Computing | Concepts only — nothing provisioned |
| 2 | Networking — VPCs | VPC (`10.0.0.0/22`), 4 subnets, internet gateway, route tables |
| 3 | EC2 | t3.micro AL2023 instance, key pair, Elastic IP, security group, AMI, launch template, backup instance |
| 4 | RDS | Postgres primary + read replica, private subnet group, security group |
| 5–11 | IAM, CloudWatch, Route 53, S3, CloudFront, ECS, Lambda | Planned — added as the course progresses |

## Prerequisites

- An AWS account (free tier covers most of the course).
- AWS credentials available to Pulumi (AWS CLI profile or environment variables).
- [Pulumi CLI](https://www.pulumi.com/docs/install/) installed and logged in.
- Python 3.12+ and [uv](https://docs.astral.sh/uv/) — the project manages dependencies with uv.

## Getting started

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Configure the stack secrets:

   ```bash
   pulumi config set --secret local_ip "$(curl -s ifconfig.me)"
   pulumi config set --secret rds_master_password "your-strong-password"
   ```

   - `local_ip` — your public IP, whitelisted for SSH in the EC2 security
     group. Re-run whenever your IP changes.
   - `rds_master_password` — the Postgres master password for RDS.

3. Preview and deploy:

   ```bash
   pulumi preview
   pulumi up
   ```

4. Connect to the web instance (the SSH key is generated on the first deploy):

   ```bash
   ssh -i ~/.ssh/patientping-key ec2-user@$(pulumi stack output ec2_eip_public_ip)
   ```

5. Connect to the database **from the instance** — the RDS security group
   only accepts connections from the EC2 security group:

   ```bash
   psql -h <endpoint-host> -U postgres -d patientping
   ```

   Get the host from `pulumi stack output rds_instance_endpoint`.

6. Tear everything down when you're done:

   ```bash
   pulumi destroy
   ```

## Project layout

```
├── __main__.py        # Entry point: wires the chapters together, exports outputs
├── config.py          # Stack configuration (env name, secrets)
├── components/
│   ├── networking.py  # Ch 2: VPC, subnets, internet gateway, route tables
│   ├── compute.py     # Ch 3: EC2 instance, key pair, Elastic IP, security group
│   ├── snapshots.py   # Ch 3: AMI and launch template of the web instance
│   ├── backups.py     # Ch 3: backup instance built from the launch template
│   └── data_plane.py  # Ch 4: RDS Postgres primary + read replica
├── Pulumi.yaml        # Project metadata
└── Pulumi.dev.yaml    # Stack config (region, secrets)
```

## Configuration

| Key | Type | Purpose |
|---|---|---|
| `aws:region` | string | Deployment region — `eu-west-2` |
| `local_ip` | secret | Your public IP, allowed for SSH ingress |
| `rds_master_password` | secret | Postgres master password for RDS |

## Stack outputs

- `vpc_id`, `vpc_subnets`, `vpc_igw`, `vpc_public_rt`
- `ec2_id`, `ec2_public_sg_id`, `ec2_keypair`, `ec2_eip_public_ip`
- `ec2_ami_id`, `ec2_launch_template_id`, `ec2_backup_id`
- `rds_instance_endpoint`, `rds_replica_instance_endpoint`

Inspect them with `pulumi stack output`.

## A note on cost

RDS (even t3.micro) and Elastic IPs are **not** free tier. The Elastic IP
also bills while the instance is stopped. If you're not actively working
through a chapter, run `pulumi destroy` to avoid surprise charges.
