# AWS Resource Inventory

This file records the temporary Know Your Lease production resources created by
Phase 6B. It contains identifiers and teardown instructions only; never put
passwords, database URLs, API keys, or other secret values here.

## Deployment metadata

| Field | Value |
| --- | --- |
| AWS account | `297784246437` |
| Region | `ca-central-1` |
| Project tag | `Project=KnowYourLease` |
| Environment tag | `Environment=production` |
| Temporary tag | `TemporaryDeployment=true` |
| Intended lifetime | Approximately three days for portfolio validation |
| Provisioning status | Phase 6B complete; resources retained for later phases |

## Live account constraints and deviations

- The first RDS create request was rejected with `FreeTierRestrictionError` before
  an instance was created because this AWS Free plan does not allow the requested
  seven-day backup retention. The temporary instance therefore uses one-day
  automated-backup retention. Deletion protection remains enabled, and teardown
  must still make an explicit final-snapshot decision.

The CLI identity used for Phase 6B preflight was
`arn:aws:iam::297784246437:root`. Use a least-privilege administrative role for
future deployments where practical.

## Resources

Resource rows were added immediately after each successful create operation.

| Resource type | Name | ARN/ID | Region | Purpose | Ongoing cost | Teardown command/note |
| --- | --- | --- | --- | --- | --- | --- |
| VPC | `know-your-lease-prod-vpc` | `vpc-01483dc7b718ba50b` | `ca-central-1` | Isolated project network, `10.0.0.0/16` | No fixed charge | After dependents: `aws ec2 delete-vpc --region ca-central-1 --vpc-id vpc-01483dc7b718ba50b` |
| VPC main route table | `know-your-lease-prod-main-rt` | `rtb-0bebd84ad26b54eb6` | `ca-central-1` | AWS-created main table; local route only and unused by project subnets | No fixed charge | Deleted automatically with the VPC |
| VPC default security group | `know-your-lease-prod-default-sg` | `sg-0798e72293db96aea` | `ca-central-1` | AWS-created default group; all ingress and egress removed | No fixed charge | Deleted automatically with the VPC |
| VPC default network ACL | `know-your-lease-prod-default-nacl` | `acl-06d1cba227e8ee367` | `ca-central-1` | AWS-created default stateless subnet ACL | No fixed charge | Deleted automatically with the VPC |
| Public subnet | `know-your-lease-prod-public-a` | `subnet-080fd53bdbddc83b0` | `ca-central-1a` | Future ALB/ECS, `10.0.0.0/24` | No fixed charge | `aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-080fd53bdbddc83b0` |
| Public subnet | `know-your-lease-prod-public-b` | `subnet-0873f662451c39799` | `ca-central-1b` | Future ALB/ECS, `10.0.1.0/24` | No fixed charge | `aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0873f662451c39799` |
| Isolated DB subnet | `know-your-lease-prod-db-a` | `subnet-0f654d62e88ed4e98` | `ca-central-1a` | RDS, `10.0.10.0/24` | No fixed charge | After RDS/subnet-group deletion: `aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0f654d62e88ed4e98` |
| Isolated DB subnet | `know-your-lease-prod-db-b` | `subnet-0b362ea1503ba535e` | `ca-central-1b` | RDS, `10.0.11.0/24` | No fixed charge | After RDS/subnet-group deletion: `aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0b362ea1503ba535e` |
| Internet Gateway | `know-your-lease-prod-igw` | `igw-0dcbc7f5e4f3723ad` | `ca-central-1` | Internet route for future public ALB/ECS subnets | No fixed charge | Detach, then `aws ec2 delete-internet-gateway --region ca-central-1 --internet-gateway-id igw-0dcbc7f5e4f3723ad` |
| Public route table | `know-your-lease-prod-public-rt` | `rtb-0f006aa35bfda99ca` | `ca-central-1` | Public subnets via associations `rtbassoc-0943720ce681d77d8`, `rtbassoc-097cd2cb4658c7fbc`; IGW and S3 endpoint routes | No fixed charge | Disassociate both association IDs, then `aws ec2 delete-route-table --region ca-central-1 --route-table-id rtb-0f006aa35bfda99ca` |
| DB route table | `know-your-lease-prod-db-rt` | `rtb-01443693daaf9476c` | `ca-central-1` | Isolated DB subnets via `rtbassoc-08e63943e5300e939`, `rtbassoc-03317c618b124ac53`; local route only | No fixed charge | Disassociate both association IDs, then `aws ec2 delete-route-table --region ca-central-1 --route-table-id rtb-01443693daaf9476c` |
| S3 Gateway endpoint | `know-your-lease-prod-s3-endpoint` | `vpce-0cd817d62ca77828a` | `ca-central-1` | Private S3 route on `rtb-0f006aa35bfda99ca` | No hourly charge | `aws ec2 delete-vpc-endpoints --region ca-central-1 --vpc-endpoint-ids vpce-0cd817d62ca77828a` |
| Security group | `know-your-lease-prod-alb-sg` | `sg-07d87eca20e784665` | `ca-central-1` | Future ALB ingress on 80/443; egress only to API port 8000 | No fixed charge | Remove references, then `aws ec2 delete-security-group --region ca-central-1 --group-id sg-07d87eca20e784665` |
| Security group | `know-your-lease-prod-api-sg` | `sg-0a522d046f50f1648` | `ca-central-1` | API ingress only from ALB; HTTPS, DNS, and DB egress | No fixed charge | Remove references, then `aws ec2 delete-security-group --region ca-central-1 --group-id sg-0a522d046f50f1648` |
| Security group | `know-your-lease-prod-worker-sg` | `sg-07296ff1077ef4e27` | `ca-central-1` | No ingress; HTTPS, DNS, and DB egress | No fixed charge | Remove references, then `aws ec2 delete-security-group --region ca-central-1 --group-id sg-07296ff1077ef4e27` |
| Security group | `know-your-lease-prod-migration-sg` | `sg-0c72374cad38edac2` | `ca-central-1` | No ingress; HTTPS, DNS, and DB egress | No fixed charge | Remove references, then `aws ec2 delete-security-group --region ca-central-1 --group-id sg-0c72374cad38edac2` |
| Security group | `know-your-lease-prod-rds-sg` | `sg-0da4b34da87742d35` | `ca-central-1` | PostgreSQL ingress from API, worker, and migration groups only; no egress | No fixed charge | Delete RDS first, remove ingress references, then `aws ec2 delete-security-group --region ca-central-1 --group-id sg-0da4b34da87742d35` |
| RDS DB subnet group | `know-your-lease-prod-db-subnets` | `arn:aws:rds:ca-central-1:297784246437:subgrp:know-your-lease-prod-db-subnets` | `ca-central-1` | Restricts RDS to the two isolated DB subnets | No separate charge | After DB deletion: `aws rds delete-db-subnet-group --region ca-central-1 --db-subnet-group-name know-your-lease-prod-db-subnets` |
| RDS PostgreSQL | `know-your-lease-prod` | `arn:aws:rds:ca-central-1:297784246437:db:know-your-lease-prod` | `ca-central-1` | PostgreSQL 18.6, Single-AZ `db.t4g.micro`, 20 GiB gp3, max 50 GiB; private endpoint `know-your-lease-prod.czukqicy26su.ca-central-1.rds.amazonaws.com:5432` | Yes; primary Phase 6B cost | First disable protection: `aws rds modify-db-instance --region ca-central-1 --db-instance-identifier know-your-lease-prod --no-deletion-protection --apply-immediately`; after confirming no data must remain, delete with `aws rds delete-db-instance --region ca-central-1 --db-instance-identifier know-your-lease-prod --skip-final-snapshot --delete-automated-backups` |
| RDS-managed master secret | `rds!db-ca7ef035-6f1f-48cf-8f62-30d9f6b0d639` | `arn:aws:secretsmanager:ca-central-1:297784246437:secret:rds!db-ca7ef035-6f1f-48cf-8f62-30d9f6b0d639-vEm6Og` | `ca-central-1` | RDS-generated master credential; secret value is not recorded | Yes; Secrets Manager per-secret charge | Expected to follow RDS lifecycle; after DB deletion verify with `aws secretsmanager describe-secret --region ca-central-1 --secret-id <ARN>` and delete separately only if AWS did not remove it |
| RDS automated snapshot | `rds:know-your-lease-prod-2026-09-04-20-55` | `arn:aws:rds:ca-central-1:297784246437:snapshot:rds:know-your-lease-prod-2026-09-04-20-55` | `ca-central-1` | RDS-managed automated backup under one-day retention | Normally covered by included backup allocation at this size | Managed by RDS retention; `--delete-automated-backups` on DB teardown removes retained automated backups |
| S3 bucket | `know-your-lease-prod-297784246437-ca-central-1` | `arn:aws:s3:::know-your-lease-prod-297784246437-ca-central-1` | `ca-central-1` | Private PDFs under `uploads/<document-uuid>.pdf` | Usage-based only | Confirm target, remove objects/versions if any, then `aws s3api delete-bucket --region ca-central-1 --bucket know-your-lease-prod-297784246437-ca-central-1` |
| SQS DLQ | `know-your-lease-ingestion-prod-dlq` | `arn:aws:sqs:ca-central-1:297784246437:know-your-lease-ingestion-prod-dlq` | `ca-central-1` | Encrypted 14-day dead-letter retention | Usage-based only | `aws sqs delete-queue --region ca-central-1 --queue-url https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod-dlq` |
| SQS queue | `know-your-lease-ingestion-prod` | `arn:aws:sqs:ca-central-1:297784246437:know-your-lease-ingestion-prod` | `ca-central-1` | Encrypted ingestion queue; 900-second visibility, 20-second long polling, four-day retention, DLQ after five receives | Usage-based only | Delete before DLQ: `aws sqs delete-queue --region ca-central-1 --queue-url https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod` |

## Required teardown order

Later phases may add application services that must be removed before these data
plane resources. For the Phase 6B resources, use this dependency order:

1. Remove later ECS/ALB resources, IAM dependencies, and application secrets.
2. Delete the main queue, then the DLQ:

   ```bash
   aws sqs delete-queue --region ca-central-1 --queue-url https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod
   aws sqs delete-queue --region ca-central-1 --queue-url https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod-dlq
   ```

3. Confirm the S3 target, empty it if later phases uploaded disposable objects,
   then delete it:

   ```bash
   aws s3 rm s3://know-your-lease-prod-297784246437-ca-central-1 --recursive
   aws s3api delete-bucket --region ca-central-1 --bucket know-your-lease-prod-297784246437-ca-central-1
   ```

4. The temporary-data policy is to skip the final RDS snapshot only after a human
   confirms that no data must be retained. Disable protection, wait, delete, and
   wait again:

   ```bash
   aws rds modify-db-instance --region ca-central-1 --db-instance-identifier know-your-lease-prod --no-deletion-protection --apply-immediately
   aws rds wait db-instance-available --region ca-central-1 --db-instance-identifier know-your-lease-prod
   aws rds delete-db-instance --region ca-central-1 --db-instance-identifier know-your-lease-prod --skip-final-snapshot --delete-automated-backups
   aws rds wait db-instance-deleted --region ca-central-1 --db-instance-identifier know-your-lease-prod
   ```

   If data must be retained, replace `--skip-final-snapshot` with
   `--final-db-snapshot-identifier <reviewed-unique-name>` and omit
   `--delete-automated-backups`; that retained snapshot will continue billing.

5. Delete the DB subnet group after RDS is gone. Verify the RDS-managed secret was
   removed by RDS; do not independently delete it while the DB exists:

   ```bash
   aws rds delete-db-subnet-group --region ca-central-1 --db-subnet-group-name know-your-lease-prod-db-subnets
   aws secretsmanager describe-secret --region ca-central-1 --secret-id arn:aws:secretsmanager:ca-central-1:297784246437:secret:rds!db-ca7ef035-6f1f-48cf-8f62-30d9f6b0d639-vEm6Og
   ```

6. Delete the S3 gateway endpoint:

   ```bash
   aws ec2 delete-vpc-endpoints --region ca-central-1 --vpc-endpoint-ids vpce-0cd817d62ca77828a
   ```

7. Remove cross-group references, then delete the five custom security groups:

   ```bash
   aws ec2 revoke-security-group-egress --region ca-central-1 --group-id sg-07d87eca20e784665 --security-group-rule-ids sgr-0810466543f22e593
   aws ec2 revoke-security-group-ingress --region ca-central-1 --group-id sg-0a522d046f50f1648 --security-group-rule-ids sgr-0df6b415de6049950
   aws ec2 revoke-security-group-ingress --region ca-central-1 --group-id sg-0da4b34da87742d35 --security-group-rule-ids sgr-0153f0527ab98f283 sgr-04bfbed1733fef15d sgr-0ece582bf7c4a6043
   aws ec2 revoke-security-group-egress --region ca-central-1 --group-id sg-0a522d046f50f1648 --security-group-rule-ids sgr-0859ed2c2ae4ca6f3
   aws ec2 revoke-security-group-egress --region ca-central-1 --group-id sg-07296ff1077ef4e27 --security-group-rule-ids sgr-07a9fd6431231298c
   aws ec2 revoke-security-group-egress --region ca-central-1 --group-id sg-0c72374cad38edac2 --security-group-rule-ids sgr-09980249f1b9ca8c1
   aws ec2 delete-security-group --region ca-central-1 --group-id sg-07d87eca20e784665
   aws ec2 delete-security-group --region ca-central-1 --group-id sg-0a522d046f50f1648
   aws ec2 delete-security-group --region ca-central-1 --group-id sg-07296ff1077ef4e27
   aws ec2 delete-security-group --region ca-central-1 --group-id sg-0c72374cad38edac2
   aws ec2 delete-security-group --region ca-central-1 --group-id sg-0da4b34da87742d35
   ```

8. Disassociate the four subnets and delete the custom route tables:

   ```bash
   aws ec2 disassociate-route-table --region ca-central-1 --association-id rtbassoc-0943720ce681d77d8
   aws ec2 disassociate-route-table --region ca-central-1 --association-id rtbassoc-097cd2cb4658c7fbc
   aws ec2 disassociate-route-table --region ca-central-1 --association-id rtbassoc-08e63943e5300e939
   aws ec2 disassociate-route-table --region ca-central-1 --association-id rtbassoc-03317c618b124ac53
   aws ec2 delete-route-table --region ca-central-1 --route-table-id rtb-0f006aa35bfda99ca
   aws ec2 delete-route-table --region ca-central-1 --route-table-id rtb-01443693daaf9476c
   ```

9. Detach and delete the Internet Gateway:

   ```bash
   aws ec2 detach-internet-gateway --region ca-central-1 --internet-gateway-id igw-0dcbc7f5e4f3723ad --vpc-id vpc-01483dc7b718ba50b
   aws ec2 delete-internet-gateway --region ca-central-1 --internet-gateway-id igw-0dcbc7f5e4f3723ad
   ```

10. Delete the subnets and VPC; the main route table, default security group, and
    default network ACL are removed with the VPC:

    ```bash
    aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-080fd53bdbddc83b0
    aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0873f662451c39799
    aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0f654d62e88ed4e98
    aws ec2 delete-subnet --region ca-central-1 --subnet-id subnet-0b362ea1503ba535e
    aws ec2 delete-vpc --region ca-central-1 --vpc-id vpc-01483dc7b718ba50b
    ```

Never delete a resource solely because its name looks similar. Resolve and verify
every ID against this inventory and the three project tags first.

## Verified Phase 6B state

- VPC DNS support and DNS hostnames are enabled.
- Public subnets use `rtb-0f006aa35bfda99ca`, whose only default route is the
  project Internet Gateway. The S3 managed-prefix route targets the gateway
  endpoint. Subnet-level public-IP auto-assignment remains off; later ECS task
  definitions must explicitly use `assignPublicIp=ENABLED`.
- DB subnets use `rtb-01443693daaf9476c`, which contains only the local VPC route.
- No NAT gateway, Elastic IP, EC2 instance, ALB, ECS cluster, or ECR repository
  was created for this project.
- RDS is private, Single-AZ, encrypted, deletion-protected, and attached only to
  `sg-0da4b34da87742d35`. The PostgreSQL 18 default parameter group reports
  `rds.force_ssl=1`.
- RDS ingress is PostgreSQL 5432 from only the API, worker, and migration security
  groups. Worker and migration groups have no ingress. API 8000 is ALB-group-only.
- The S3 bucket is empty and non-public, has all four public-access blocks,
  BucketOwnerEnforced ownership, AES-256 default encryption, a TLS-only policy,
  no CORS, no website, and no PDF expiration rule.
- Both SQS queues are empty and use SQS-managed encryption. The main queue uses
  900-second visibility, 20-second long polling, four-day retention, and redrives
  to the 14-day DLQ after five receives.

## Pgvector readiness

The repository's base Alembic migration `20260806_0001` already runs
`CREATE EXTENSION IF NOT EXISTS vector`. The RDS endpoint is intentionally private,
and Phase 6B creates no compute inside the VPC, so the extension has not yet been
executed or queried on this instance. Pgvector must be verified after the Phase 6D
migration task runs; this inventory does not claim it is currently active.

## Current list-price estimate

AWS's live price list for Canada Central reports `db.t4g.micro` PostgreSQL
Single-AZ at `$0.018/hour` and gp3 at `$0.127/GB-month`. At 20 GiB, that is about
`$0.52/day` or `$15.68/month` for RDS compute and storage. The RDS-managed secret
adds approximately `$0.013/day` or `$0.40/month`, for a Phase 6B list-price total
of approximately **$0.53/day or $16.08/month**, before tax, credits, backup excess,
requests, or transfer. The account's Free plan/credits may reduce the billed total.

No NAT Gateway, ALB, Fargate task, public IPv4 allocation, provisioned IOPS,
Performance Insights, or enhanced RDS monitoring is active. The VPC, subnets,
route tables, Internet Gateway, security groups, and S3 Gateway endpoint have no
fixed hourly charge; empty S3/SQS usage is negligible.
