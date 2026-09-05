# AWS Resource Inventory

This file records the temporary Know Your Lease production resources created by
Phase 6B and Phase 6C. It contains identifiers and teardown instructions only;
never put passwords, database URLs, API keys, access key secret values, or other
secret material here.

## Deployment metadata

| Field | Value |
| --- | --- |
| AWS account | `297784246437` |
| Region | `ca-central-1` |
| Project tag | `Project=KnowYourLease` |
| Environment tag | `Environment=production` |
| Temporary tag | `TemporaryDeployment=true` |
| Intended lifetime | Approximately three days for portfolio validation |
| Provisioning status | Phase 6B and 6C complete; resources retained for later phases |
| Routine CLI identity | `arn:aws:iam::297784246437:user/kyl-deployer` (profile `kyl-deploy`), as of Phase 6C -- see [aws-identity.md](aws-identity.md) |

## Live account constraints and deviations

- The first RDS create request was rejected with `FreeTierRestrictionError` before
  an instance was created because this AWS Free plan does not allow the requested
  seven-day backup retention. The temporary instance therefore uses one-day
  automated-backup retention. Deletion protection remains enabled, and teardown
  must still make an explicit final-snapshot decision.
- `CreateUserPool` rejected `MfaConfiguration=OPTIONAL` without SMS/SNS configured.
  The pool was created with MFA `OFF`, then `set-user-pool-mfa-config` enabled
  `OPTIONAL` with software-token (TOTP) MFA only -- no SMS, no SNS role, no
  per-message cost.

The CLI identity used for Phase 6B preflight and the first half of Phase 6C
(creating `kyl-deployer` itself, which nothing else could do) was
`arn:aws:iam::297784246437:root`. Every other Phase 6C resource, and all routine
work from here forward, uses `kyl-deployer`. See
[aws-identity.md](aws-identity.md) for the full remediation record, including why
`aws login` could not be used for the non-root identity in this session and what
was verified before and after the switch.

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
| IAM customer-managed policy | `KnowYourLeaseDeployerPolicy` | `arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy` | `ca-central-1` (IAM is global) | Scoped admin policy for the temporary deployment identity; explicit Deny on `freetier:UpgradeAccountPlan`, `organizations:*`, new IAM users/access keys, and self-lockout on `kyl-deployer` | No fixed charge | Detach from `kyl-deployer` last, then `aws iam delete-policy --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy` |
| IAM user | `kyl-deployer` | `arn:aws:iam::297784246437:user/kyl-deployer` | `ca-central-1` (IAM is global) | Non-root deployment identity; console login profile exists (password-reset-required, unused this session) and one access key exists for the `kyl-deploy` CLI profile; no `AdministratorAccess` | No fixed charge | Last of all Phase 6C resources: delete the access key, delete the login profile, detach `KnowYourLeaseDeployerPolicy`, then `aws iam delete-user --user-name kyl-deployer` |
| Cognito user pool | `know-your-lease-prod` | `ca-central-1_Lhw9u8Yh6` | `ca-central-1` | LITE tier, email sign-in/verification, self-signup, optional TOTP MFA, advanced security OFF, deletion protection ACTIVE | Per-MAU only (~$0.0055/MAU at LITE, verified live price list) | First disable protection: `aws cognito-idp update-user-pool --user-pool-id ca-central-1_Lhw9u8Yh6 --deletion-protection INACTIVE`; delete domain and client first (see below), then `aws cognito-idp delete-user-pool --user-pool-id ca-central-1_Lhw9u8Yh6` |
| Cognito app client | `know-your-lease-web` | `4sq1r3l1flfv1acrkrqc69aoh9` (pool `ca-central-1_Lhw9u8Yh6`) | `ca-central-1` | Public SPA client, no secret, Authorization Code + PKCE only, scopes `openid email`, callbacks `http://localhost:3000/auth/callback`/`http://localhost:3000/` | No separate charge | `aws cognito-idp delete-user-pool-client --user-pool-id ca-central-1_Lhw9u8Yh6 --client-id 4sq1r3l1flfv1acrkrqc69aoh9` |
| Cognito Hosted UI domain | `know-your-lease-prod` | Domain prefix on pool `ca-central-1_Lhw9u8Yh6`; CloudFront `dq9dozspu8y40.cloudfront.net` | `ca-central-1` | Classic managed login (v1) Hosted UI; verified reachable (login page HTTP 200, JWKS HTTP 200) | No separate charge | Must be deleted before the pool: `aws cognito-idp delete-user-pool-domain --user-pool-id ca-central-1_Lhw9u8Yh6 --domain know-your-lease-prod` |
| ECR repository | `know-your-lease-backend` | `arn:aws:ecr:ca-central-1:297784246437:repository/know-your-lease-backend` | `ca-central-1` | Private, AES-256, immutable tags, basic scan-on-push, empty (no image pushed); lifecycle policy expires untagged images after 7 days and caps tagged images at 10 | $0 while empty; ~$0.10/GB-month once images exist | `aws ecr delete-repository --repository-name know-your-lease-backend --force` (force removes any images with it) |
| Secrets Manager secret | `know-your-lease/prod/voyage-api-key` | `arn:aws:secretsmanager:ca-central-1:297784246437:secret:know-your-lease/prod/voyage-api-key-sA4kXX` | `ca-central-1` | Voyage AI embeddings key; readable by `kyl-api-execution` and `kyl-worker-execution` only | ~$0.40/month + negligible API-call cost | `aws secretsmanager delete-secret --secret-id know-your-lease/prod/voyage-api-key --force-delete-without-recovery` (force avoids continued billing through a recovery window) |
| Secrets Manager secret | `know-your-lease/prod/gemini-api-key` | `arn:aws:secretsmanager:ca-central-1:297784246437:secret:know-your-lease/prod/gemini-api-key-8gTg9j` | `ca-central-1` | Gemini generation key; readable by `kyl-api-execution` only | ~$0.40/month + negligible API-call cost | `aws secretsmanager delete-secret --secret-id know-your-lease/prod/gemini-api-key --force-delete-without-recovery` |
| IAM role (execution) | `kyl-api-execution` | `arn:aws:iam::297784246437:role/kyl-api-execution` | `ca-central-1` (IAM is global) | ECS execution role: `AmazonECSTaskExecutionRolePolicy` + inline `KnowYourLeaseApiSecrets` (Voyage, Gemini, and a not-yet-created `database-url-app` by name prefix) | No fixed charge | Delete inline policy, detach managed policy, then `aws iam delete-role --role-name kyl-api-execution` |
| IAM role (execution) | `kyl-worker-execution` | `arn:aws:iam::297784246437:role/kyl-worker-execution` | `ca-central-1` (IAM is global) | ECS execution role: `AmazonECSTaskExecutionRolePolicy` + inline `KnowYourLeaseWorkerSecrets` (Voyage and a not-yet-created `database-url-app`; no Gemini) | No fixed charge | Delete inline policy, detach managed policy, then `aws iam delete-role --role-name kyl-worker-execution` |
| IAM role (execution) | `kyl-migration-execution` | `arn:aws:iam::297784246437:role/kyl-migration-execution` | `ca-central-1` (IAM is global) | ECS execution role: `AmazonECSTaskExecutionRolePolicy` + inline `KnowYourLeaseMigrationSecrets` (references a not-yet-created `database-url-migrate`; grants nothing today) | No fixed charge | Delete inline policy, detach managed policy, then `aws iam delete-role --role-name kyl-migration-execution` |
| IAM role (task) | `kyl-api-task` | `arn:aws:iam::297784246437:role/kyl-api-task` | `ca-central-1` (IAM is global) | Application role for the API container: inline `KnowYourLeaseApiDataAccess` grants `s3:GetObject`/`PutObject`/`DeleteObject` on `uploads/*` only and `sqs:SendMessage` on the main queue only; no ListBucket, no Receive, no DLQ | No fixed charge | Delete inline policy, then `aws iam delete-role --role-name kyl-api-task` |
| IAM role (task) | `kyl-worker-task` | `arn:aws:iam::297784246437:role/kyl-worker-task` | `ca-central-1` (IAM is global) | Application role for the worker container: inline `KnowYourLeaseWorkerDataAccess` grants `s3:GetObject` on `uploads/*` only and `sqs:ReceiveMessage`/`DeleteMessage` on the main queue only; no Put/Delete, no Send, no ChangeMessageVisibility, no DLQ | No fixed charge | Delete inline policy, then `aws iam delete-role --role-name kyl-worker-task` |

The migration workload has no task role at all: it makes no AWS API calls beyond
what its execution role already grants (image pull, log write, its one secret).

## Required teardown order (Phase 6C, before Phase 6B)

Phase 6C resources sit above the Phase 6B data plane and must be removed first if
the whole deployment is torn down. No Phase 6D/ECS resources exist to remove
before this. In order:

1. Detach the inline policy from and delete `kyl-api-task`, then `kyl-worker-task`:

   ```bash
   aws iam delete-role-policy --role-name kyl-api-task --policy-name KnowYourLeaseApiDataAccess
   aws iam delete-role --role-name kyl-api-task
   aws iam delete-role-policy --role-name kyl-worker-task --policy-name KnowYourLeaseWorkerDataAccess
   aws iam delete-role --role-name kyl-worker-task
   ```

2. Delete the inline policy and detach the managed policy from each execution
   role, then delete the role:

   ```bash
   for role in kyl-api-execution kyl-worker-execution kyl-migration-execution; do
     policy_name=$(aws iam list-role-policies --role-name "$role" --query 'PolicyNames[0]' --output text)
     aws iam delete-role-policy --role-name "$role" --policy-name "$policy_name"
     aws iam detach-role-policy --role-name "$role" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
     aws iam delete-role --role-name "$role"
   done
   ```

3. Force-delete both application secrets so recovery-window billing does not
   continue after teardown:

   ```bash
   aws secretsmanager delete-secret --secret-id know-your-lease/prod/voyage-api-key --force-delete-without-recovery
   aws secretsmanager delete-secret --secret-id know-your-lease/prod/gemini-api-key --force-delete-without-recovery
   ```

4. Delete any images, then the ECR repository:

   ```bash
   aws ecr delete-repository --repository-name know-your-lease-backend --force
   ```

5. Delete the Cognito domain, then the app client, then the user pool, in that
   exact order (the pool cannot be deleted while a domain is attached):

   ```bash
   aws cognito-idp delete-user-pool-domain --user-pool-id ca-central-1_Lhw9u8Yh6 --domain know-your-lease-prod
   aws cognito-idp delete-user-pool-client --user-pool-id ca-central-1_Lhw9u8Yh6 --client-id 4sq1r3l1flfv1acrkrqc69aoh9
   aws cognito-idp update-user-pool --user-pool-id ca-central-1_Lhw9u8Yh6 --deletion-protection INACTIVE
   aws cognito-idp delete-user-pool --user-pool-id ca-central-1_Lhw9u8Yh6
   ```

6. Last of all: delete `kyl-deployer`'s access key, delete its login profile,
   detach `KnowYourLeaseDeployerPolicy`, delete the user, then delete the policy.
   Do this only after every resource above is gone -- deleting the deployer first
   removes the only non-root path capable of the earlier steps.

   ```bash
   aws iam list-access-keys --user-name kyl-deployer   # get the key id, then:
   aws iam delete-access-key --user-name kyl-deployer --access-key-id <id-from-above>
   aws iam delete-login-profile --user-name kyl-deployer
   aws iam detach-user-policy --user-name kyl-deployer --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy
   aws iam delete-user --user-name kyl-deployer
   aws iam delete-policy --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy
   ```

   The last two steps must run as root (or from another admin identity), since
   `kyl-deployer` is deleting itself. Root console access is retained specifically
   for this kind of break-glass step.

## Required teardown order (Phase 6B)

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
- No NAT gateway, Elastic IP, EC2 instance, ALB, or ECS cluster was created for
  this project. (An ECR repository was created in Phase 6C -- see below.)
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

## Verified Phase 6C state

All of the following were confirmed live with `describe-*`/`get-*`/`simulate-principal-policy`
calls, not assumed from creation parameters:

- `aws sts get-caller-identity --profile kyl-deploy` returns
  `arn:aws:iam::297784246437:user/kyl-deployer`, not root.
- Root: `AccountAccessKeysPresent=0` (still no root access keys), root has a
  console login profile with a password reset required and no MFA enrolled at
  the end of this session -- see [aws-identity.md](aws-identity.md) for the
  outstanding manual step.
- The account remains `accountPlanType=FREE`, `accountPlanStatus=ACTIVE`, with
  `$120.00 USD` remaining credit, both before and after all Phase 6C creates.
- The account is still not a member of an AWS Organization (verified via root,
  since `kyl-deployer`'s policy denies all `organizations:*` actions including
  the read-only describe call -- this is the guardrail working as intended, not
  a gap).
- Cognito pool `ca-central-1_Lhw9u8Yh6`: `UserPoolTier=LITE`,
  `UserPoolAddOns.AdvancedSecurityMode=OFF`, `MfaConfiguration=OPTIONAL` with
  `SoftwareTokenMfaConfiguration.Enabled=true` and no SMS configuration.
- App client `4sq1r3l1flfv1acrkrqc69aoh9`: no `ClientSecret` field in the create
  response, `AllowedOAuthFlows=["code"]` only (no `implicit`),
  `AllowedOAuthScopes=["openid","email"]`,
  `SupportedIdentityProviders=["COGNITO"]`, access/ID token validity 60 minutes,
  refresh token validity 30 days.
- Domain `know-your-lease-prod`: `Status=ACTIVE`, `ManagedLoginVersion=1`. The
  JWKS endpoint
  (`https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_Lhw9u8Yh6/.well-known/jwks.json`)
  returned HTTP 200; the OIDC discovery document's `issuer` and `jwks_uri` match
  what `backend/app/core/config.py`'s `cognito_issuer_url`/`cognito_jwks_url`
  derive from `COGNITO_REGION`/`COGNITO_USER_POOL_ID`; the Hosted UI login page
  returned HTTP 200.
- ECR repository: `imageTagMutability=IMMUTABLE`, `encryptionType=AES256`,
  `scanOnPush=true` (basic scanning; Inspector/enhanced scanning was never
  enabled), zero images. `docker login` against the registry succeeded via
  `kyl-deployer` and the credential was removed immediately after (no image
  pushed).
- Both secrets (`voyage-api-key`, `gemini-api-key`) confirmed present via
  `describe-secret` (metadata only); `get-secret-value` was never called during
  verification and no value was displayed, logged, or written anywhere in this
  repository.
- IAM policy simulation (`iam:SimulatePrincipalPolicy`), 17 cases, all matched
  intent: `kyl-api-task` can `PutObject`/`GetObject`/`DeleteObject` on
  `uploads/*` and `SendMessage` on the main queue; `kyl-worker-task` can
  `GetObject` on `uploads/*` and `ReceiveMessage`/`DeleteMessage` on the main
  queue. Both are denied the other's write/receive actions, `ListBucket`,
  `ChangeMessageVisibility`, `SendMessage` to the DLQ, and any DLQ access at all.
- A second simulation set confirmed `kyl-api-execution` and `kyl-worker-execution`
  can read `voyage-api-key`; only `kyl-api-execution` can read `gemini-api-key`;
  `kyl-migration-execution` can read neither; and none of the three roles can
  read the RDS-managed master secret.
- No role or policy created in Phase 6C contains `s3:*`, `sqs:*`,
  `secretsmanager:*`, or an attached `AdministratorAccess` policy (checked by
  reading every inline policy document back and every attached managed policy
  list, not by inspection of the source JSON alone).
- No task role exists for the migration workload
  (`aws iam get-role --role-name kyl-migration-task` returns `NoSuchEntity`).
- No CloudWatch log group exists under `/ecs/know-your-lease` (Phase 6D's job).
- No static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` appears anywhere in
  `backend/.env`, either `.env.example`, or `docker-compose.yml`.

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

### Phase 6C incremental cost

Live AWS Price List data for Canada Central: Secrets Manager `$0.40/secret-month`
plus `$0.05/10,000 API requests`; Cognito Lite tier `$0.0055/MAU`; ECR
`$0.10/GB-month` (storage only, billed from the first pushed image); IAM has no
charge at any usage level.

| Item | Monthly | Daily |
| --- | ---: | ---: |
| 2 secrets (`voyage-api-key`, `gemini-api-key`) | $0.80 | $0.026 |
| Cognito (portfolio-scale MAU, Lite tier) | < $0.03 | < $0.001 |
| ECR (repository empty, no image pushed) | $0.00 | $0.00 |
| IAM (5 roles, 1 policy, 1 user) | $0.00 | $0.00 |
| **Phase 6C total** | **≈ $0.83** | **≈ $0.028** |
| Phase 6B total (unchanged) | $16.08 | $0.53 |
| **Running total** | **≈ $16.91** | **≈ $0.56** |

This is list price before tax; the Free plan's remaining $120.00 credit absorbs
it, and the account's payable amount was confirmed at $0 both before and after
Phase 6C. ECR storage becomes billable once Phase 6D or later pushes an image.
