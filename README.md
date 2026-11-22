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
| 5 | IAM + SSM | IAM user, group + membership, EC2 read-only policy, EC2 role + instance profile, `/DATABASE_URL` + `/CMO_NAME` SSM parameters, SSM access policy |
| 6 | CloudWatch | Dashboard, EC2 monitoring role/profile, logs, and custom memory/swap metrics |
| 7–11 | Route 53, S3, CloudFront, ECS, Lambda | Planned — added as the course progresses |

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

2. Configure the stack:

   ```bash
   pulumi config set --secret local_ip "$(curl -s ifconfig.me)"
   pulumi config set --secret rds_master_password "your-strong-password"
   pulumi config set cmo_name "Dr. Strangelove"
   ```

   - `local_ip` — your public IPv4 address, whitelisted for SSH in the EC2
     security group. Use `curl -4` explicitly because VPNs and dual-stack networks may otherwise return an IPv6 address. Re-run whenever your IP changes.
   - `rds_master_password` — the Postgres master password for RDS.
   - `cmo_name` — the CMO name, stored in the `/CMO_NAME` SSM parameter.

3. Preview and deploy:

   ```bash
   pulumi preview
   pulumi up
   ```

4. Connect to the web instance (the SSH key is generated on the first deploy):

   ```bash
   ssh -i ~/.ssh/patientping-key ec2-user@$(pulumi stack output ec2_eip_public_ip)
   ```

5. Deploy the web application server. Run these commands **on the instance**:

   ```bash
   # Install dependencies
   sudo dnf upgrade
   sudo dnf install git nano -y
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Clone the repo and run the server
   cd ~
   git clone https://github.com/bootdotdev/patientping-web.git
   cd patientping-web

   uv run patientping.py
   ```

   The application normally loads `DATABASE_URL` and `CMO_NAME` from SSM,
   using the AWS region configured by its runtime. The EC2 instance role grants
   access to both parameters.

   Set the region in `patientping.py` to the value of `aws:region` in
   `Pulumi.dev.yaml` (or run `pulumi config get aws:region`) before starting
   the application. If it is left at `us-east-1`, SSM returns
   `invalid parameters: ['/CMO_NAME', '/DATABASE_URL']` because the parameters
   do not exist in that region. The application falls back to `.env` only after
   this SSM lookup fails. If no `.env` file exists yet, that fallback is
   expected and can be ignored; it is not the original parameter error.

   The `.env` file is an optional local fallback for development, not a required
   replacement for SSM. To inspect the stored values on the instance:

   ```bash
   aws ssm get-parameter --name /DATABASE_URL --with-decryption \
     --query Parameter.Value --output text
   aws ssm get-parameter --name /CMO_NAME \
     --query Parameter.Value --output text
   ```

   Add `.env` only when intentionally testing the fallback:

   ```bash
   nano .env
   ```

   ```dotenv
   DATABASE_URL="<database-connection-string>"
   CMO_NAME="<name>"
   ```

   The `.env` fallback is optional. When SSM is configured correctly, no
   `.env` file is required.

6. Connect to the database **from the instance** — the RDS security group
   only accepts connections from the EC2 security group:

   ```bash
   psql -h <endpoint-host> -U postgres -d patientping
   ```

   Get the host from `pulumi stack output rds_instance_endpoint`.

7. Set up the CloudWatch Agent (chapter 6) on the EC2 instance. These
   commands run **on the instance**; use the SSH command from step 4 if needed.

   ```bash
   sudo dnf upgrade -y
   sudo dnf install amazon-cloudwatch-agent -y
   sudo nano /opt/aws/amazon-cloudwatch-agent/etc/patientping-monitoring.json
   ```

   Add this JSON configuration:

   ```json
   {
     "agent": {
       "metrics_collection_interval": 60,
       "run_as_user": "root"
     },
     "logs": {
       "logs_collected": {
         "files": {
           "collect_list": [
             {
               "file_path": "/var/log/patientping.log",
               "log_group_name": "patientping-monitoring",
               "log_stream_name": "{instance_id}"
             }
           ]
         }
       }
     },
     "metrics": {
       "append_dimensions": {
         "AutoScalingGroupName": "${aws:AutoScalingGroupName}",
         "ImageId": "${aws:ImageId}",
         "InstanceId": "${aws:InstanceId}",
         "InstanceType": "${aws:InstanceType}"
       },
       "metrics_collected": {
         "mem": { "measurement": ["mem_used_percent"] },
         "swap": { "measurement": ["swap_used_percent"] }
       }
     }
   }
   ```

   Start the agent with the saved configuration:

   ```bash
   sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
     -a fetch-config -m ec2 -s \
     -c file:/opt/aws/amazon-cloudwatch-agent/etc/patientping-monitoring.json

   sudo systemctl status amazon-cloudwatch-agent --no-pager
   sudo systemctl is-enabled amazon-cloudwatch-agent
   ```

   The instance profile provides the agent with permissions for logs,
   custom metrics, EC2 metadata, and SSM parameters. See
   `components/monitoring.py` for the IAM role and policy configuration.

   If PatientPing is still running, press `Ctrl+C` in its original SSH
   session to stop it. Start it again and write its output to the log file
   collected by the agent:

   ```bash
   cd ~/patientping-web
   PYTHONUNBUFFERED=1 uv run patientping.py 2>&1 |
     sudo tee -a /var/log/patientping.log
   ```

   Verify the setup in the AWS Console:

   - **CloudWatch → Logs → Log groups → `patientping-monitoring`**:
     open the stream named with the instance ID to see application logs.
   - **CloudWatch → Metrics → All metrics → CWAgent**:
     verify `mem_used_percent` and `swap_used_percent`.

   `DB init failed` messages are expected while RDS is stopped or deleted.

8. Tear everything down when you're done:

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
│   ├── data_plane.py  # Ch 4: RDS Postgres primary + read replica
│   ├── iam.py         # Ch 5: IAM user, group, policies, EC2 role + instance profile
│   ├── secrets.py     # Ch 5: SSM parameters + EC2 SSM access policy
│   └── monitoring.py  # Ch 6: CloudWatch dashboard, role, profile, and policies
├── Pulumi.yaml        # Project metadata
└── Pulumi.dev.yaml    # Stack config (region, secrets)
```

## Configuration

| Key | Type | Purpose |
|---|---|---|
| `aws:region` | string | Deployment region — `eu-north-1` |
| `local_ip` | string | Your public IPv4 address, allowed for SSH ingress |
| `rds_master_password` | secret | Postgres master password for RDS; baked into the `/DATABASE_URL` SSM parameter |
| `cmo_name` | string | CMO name stored in the `/CMO_NAME` SSM parameter |

## Stack outputs

- `vpc_id`, `vpc_subnets`, `vpc_igw`, `vpc_public_rt`
- `ec2_id`, `ec2_public_sg_id`, `ec2_keypair`, `ec2_eip_public_ip`
- `ec2_ami_id`, `ec2_launch_template_id`, `ec2_backup_id`
- `rds_instance_endpoint`, `rds_replica_instance_endpoint`
- `iam_user_id`, `iam_policy_id`, `iam_group_id`, `iam_user_group_membership`
- `db_url_ssm_parameter_id`, `cmo_name_ssm_parameter_id`
- `cw_dashboard_name`
- `ec2_monitoring_profile_name`
- `ec2_cloudwatch_monitoring_role_name`
- `ec2_cloudwatch_logs_access_policy_name`
- `ec2_cloudwatch_ssm_access_policy_name`

Inspect them with `pulumi stack output`.

## A note on cost

RDS (even t3.micro) and Elastic IPs are **not** free tier. The Elastic IP
also bills while the instance is stopped. If you're not actively working
through a chapter, run `pulumi destroy` to avoid surprise charges.
