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

### Phase 6D resources

| Resource type | Name | ARN/ID | Region | Purpose | Ongoing cost | Teardown command/note |
| --- | --- | --- | --- | --- | --- | --- |
| IAM policy version | `KnowYourLeaseDeployerPolicy` v2 | same policy ARN, `VersionId=v2` | global | Added ECR image-push, ECS cluster/task-def/run-task/service, CloudWatch Logs group management, ELBv2 management, and a scoped `iam:CreateServiceLinkedRole`; all 15 Phase 6C statements (including all 5 Deny guardrails) preserved byte-identical | No fixed charge | `aws iam delete-policy-version --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy --version-id v2` then `set-default-policy-version --version-id v1`, once 6D resources are gone |
| ECR image | `know-your-lease-backend` | tags `<sha>`, `<sha>-fix1`, `<sha>-fix2`; running digest `sha256:da415a7320f1324d98dfe1bf0934fbc2749f53f1f8c69f0f0da024dc2835a248` | `ca-central-1` | Production image; `<sha>` and `<sha>-fix1` are earlier same-session bootstrap-script iterations kept only because the repository is `IMMUTABLE` and nothing else references them | ~$0.10/GB-month for all tags combined (~450 MB total) | `aws ecr batch-delete-image --repository-name know-your-lease-backend --image-ids imageTag=<sha> imageTag=<sha>-fix1 imageTag=<sha>-fix2` |
| ECS cluster | `know-your-lease-prod` | `arn:aws:ecs:ca-central-1:297784246437:cluster/know-your-lease-prod` | `ca-central-1` | Fargate-only cluster; `containerInsights=disabled`; no EC2 capacity, no ECS Exec | No fixed charge (Fargate task-hours below are the real cost) | After both services and all task definitions are gone: `aws ecs delete-cluster --cluster know-your-lease-prod` |
| CloudWatch log group | `/ecs/know-your-lease/api` | same | `ca-central-1` | API container stdout/stderr, 7-day retention | Usage-based, negligible at this volume | `aws logs delete-log-group --log-group-name /ecs/know-your-lease/api` |
| CloudWatch log group | `/ecs/know-your-lease/worker` | same | `ca-central-1` | Worker container logs, 7-day retention | Usage-based, negligible | `aws logs delete-log-group --log-group-name /ecs/know-your-lease/worker` |
| CloudWatch log group | `/ecs/know-your-lease/migration` | same | `ca-central-1` | Migration + `--verify` task logs, 7-day retention | Usage-based, negligible | `aws logs delete-log-group --log-group-name /ecs/know-your-lease/migration` |
| CloudWatch log group | `/ecs/know-your-lease/bootstrap` | same | `ca-central-1` | One-off DB bootstrap task logs, 7-day retention | Usage-based, negligible | `aws logs delete-log-group --log-group-name /ecs/know-your-lease/bootstrap` |
| Secrets Manager secret | `know-your-lease/prod/database-url-app` | `arn:aws:secretsmanager:ca-central-1:297784246437:secret:know-your-lease/prod/database-url-app-FsTQ8V` | `ca-central-1` | `kyl_app` connection string (DML only, no DDL); readable by `kyl-api-execution` and `kyl-worker-execution` only | ~$0.40/month | `aws secretsmanager delete-secret --secret-id know-your-lease/prod/database-url-app --force-delete-without-recovery` |
| Secrets Manager secret | `know-your-lease/prod/database-url-migrate` | `arn:aws:secretsmanager:ca-central-1:297784246437:secret:know-your-lease/prod/database-url-migrate-6odMAo` | `ca-central-1` | `kyl_migrate` connection string (schema owner); readable by `kyl-migration-execution` only | ~$0.40/month | `aws secretsmanager delete-secret --secret-id know-your-lease/prod/database-url-migrate --force-delete-without-recovery` |
| ECS task definition | `know-your-lease-api` | family, revision 1 | `ca-central-1` | API container spec: execution `kyl-api-execution`, task `kyl-api-task`, port 8000 | No fixed charge | `aws ecs deregister-task-definition --task-definition know-your-lease-api:1` |
| ECS task definition | `know-your-lease-worker` | family, revision 1 | `ca-central-1` | Worker container spec: execution `kyl-worker-execution`, task `kyl-worker-task`, no ports | No fixed charge | `aws ecs deregister-task-definition --task-definition know-your-lease-worker:1` |
| ECS task definition | `know-your-lease-migration` | family, revision 1 | `ca-central-1` | One-off `alembic upgrade head`; execution `kyl-migration-execution`; **no task role** | No fixed charge | `aws ecs deregister-task-definition --task-definition know-your-lease-migration:1` |
| ECS task definition | `know-your-lease-bootstrap` | family, revisions 1-3 | `ca-central-1` | One-off DB role bootstrap; revisions 1-2 used a now-deleted bootstrap execution/task role pair and failed (see Bootstrap notes below); revision 3 succeeded | No fixed charge | `aws ecs deregister-task-definition --task-definition know-your-lease-bootstrap:<1\|2\|3>` |
| ECS service | `know-your-lease-api` | `arn:aws:ecs:ca-central-1:297784246437:service/know-your-lease-prod/know-your-lease-api` | `ca-central-1` | `desiredCount=1`, both public subnets, `api-sg`, registered to the ALB target group, circuit breaker + rollback enabled | Fargate task-hours (below) | `aws ecs update-service --cluster know-your-lease-prod --service know-your-lease-api --desired-count 0` then `aws ecs delete-service --cluster know-your-lease-prod --service know-your-lease-api --force` |
| ECS service | `know-your-lease-worker` | `arn:aws:ecs:ca-central-1:297784246437:service/know-your-lease-prod/know-your-lease-worker` | `ca-central-1` | `desiredCount=1`, both public subnets, `worker-sg`, no load balancer, circuit breaker + rollback enabled | Fargate task-hours (below) | Same pattern with `--service know-your-lease-worker` |
| ALB | `know-your-lease-prod` | `arn:aws:elasticloadbalancing:ca-central-1:297784246437:loadbalancer/app/know-your-lease-prod/27257d9bb115ef1a` | `ca-central-1` | Internet-facing, both public subnets, `alb-sg`; **no listener currently attached** (see below) | ~$0.024/hour + 2 public IPv4 addresses (kept per the approved Phase 6D/6E boundary) | `aws elbv2 delete-load-balancer --load-balancer-arn <arn>` (after the target group is free of the API service) |
| ALB target group | `know-your-lease-api` | `arn:aws:elasticloadbalancing:ca-central-1:297784246437:targetgroup/know-your-lease-api/4f709e08df7301ae` | `ca-central-1` | `ip` target type, HTTP:8000, health check `GET /health`, `deregistration_delay=30s`; currently one healthy target (the API task) | No separate charge | `aws elbv2 delete-target-group --target-group-arn <arn>` (after the API service stops using it) |

**Temporary bootstrap IAM (created and deleted within this same session):**
`kyl-bootstrap-execution` and `kyl-bootstrap-task` were created with a trust
policy scoped to `ecs-tasks.amazonaws.com` (`aws:SourceAccount`/`aws:SourceArn`
hardened). The task role could read only the RDS-managed master secret and
create/update only `know-your-lease/prod/database-url-*`; the execution role
carried only the AWS-managed `AmazonECSTaskExecutionRolePolicy` baseline (no
Secrets Manager access at all -- the master secret's ARN travelled as plain,
non-sensitive task configuration, and the task role fetched the value itself at
runtime). Both roles, and the task role's inline policy, were deleted
immediately after the bootstrap task exited 0 and all five hard-gate conditions
were confirmed. Verified after deletion: `simulate-principal-policy` against all
five long-lived project roles for `secretsmanager:GetSecretValue` on the RDS
master secret ARN returns `implicitDeny` for every one of them.

### Required teardown order (Phase 6D, before Phase 6C)

1. Scale both services to 0, then force-delete them (API before worker, since
   the API is the one with an external dependency on the target group):

   ```bash
   aws ecs update-service --cluster know-your-lease-prod --service know-your-lease-api --desired-count 0
   aws ecs delete-service --cluster know-your-lease-prod --service know-your-lease-api --force
   aws ecs update-service --cluster know-your-lease-prod --service know-your-lease-worker --desired-count 0
   aws ecs delete-service --cluster know-your-lease-prod --service know-your-lease-worker --force
   ```

2. Delete the target group (no listener exists to block this):

   ```bash
   aws elbv2 delete-target-group --target-group-arn arn:aws:elasticloadbalancing:ca-central-1:297784246437:targetgroup/know-your-lease-api/4f709e08df7301ae
   ```

3. Delete the ALB:

   ```bash
   aws elbv2 delete-load-balancer --load-balancer-arn arn:aws:elasticloadbalancing:ca-central-1:297784246437:loadbalancer/app/know-your-lease-prod/27257d9bb115ef1a
   ```

4. Deregister every task-definition revision (API, worker, migration, and all
   three bootstrap revisions).

5. Force-delete both database-url secrets so no recovery-window billing
   continues:

   ```bash
   aws secretsmanager delete-secret --secret-id know-your-lease/prod/database-url-app --force-delete-without-recovery
   aws secretsmanager delete-secret --secret-id know-your-lease/prod/database-url-migrate --force-delete-without-recovery
   ```

6. Delete all four log groups.

7. Delete the cluster.

8. Delete all three ECR image tags (or the whole repository, which is Phase 6C
   scope -- leave it for final teardown unless the account is being closed).

9. Revert the deployer policy to v1 (optional -- v2 is a superset with the same
   guardrails; only do this once nothing in 6D-6E era needs the extra actions):

   ```bash
   aws iam set-default-policy-version --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy --version-id v1
   aws iam delete-policy-version --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy --version-id v2
   ```

The `kyl_migrate`/`kyl_app` PostgreSQL roles live inside RDS and disappear only
when the RDS instance itself is deleted (Phase 6B teardown); there is no
separate step for them here.

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

**Active, verified.** The Phase 6D bootstrap task ran `CREATE EXTENSION IF NOT
EXISTS vector` as the RDS master user, and the Phase 6D migration task's
`--verify` run confirmed `pg_extension` contains `vector` after `alembic upgrade
head` completed. This is a live, in-VPC confirmation, not an inference from the
migration file.

## Verified Phase 6D state

All of the following were confirmed live this session, not assumed from
creation parameters:

- `KnowYourLeaseDeployerPolicy` v2 is the default version; all 15 Phase 6C
  statements (including all 5 Deny guardrails) verified byte-identical to v1
  before publishing; `simulate-principal-policy` re-confirmed
  `freetier:UpgradeAccountPlan`, `organizations:CreateOrganization`, and
  `iam:CreateUser` still evaluate as `explicitDeny` after the version bump.
- Image pushed for `linux/amd64` with `--provenance=false --sbom=false`
  (`imageManifestMediaType: application/vnd.oci.image.manifest.v1+json`, a
  single-platform manifest, not an index). Two earlier same-session iterations
  (plain SHA tag, `-fix1`) failed inside the bootstrap task before the RDS
  master secret's actual shape (`username`/`password` only, no connection
  details) and PostgreSQL's requirement that role-DDL passwords be a literal
  rather than a bind parameter were both discovered and fixed; `-fix2` is the
  digest every task definition references.
- ECS cluster `ACTIVE`, `containerInsights=disabled`, Fargate-only.
- All four log groups exist with `retentionInDays=7`.
- Bootstrap task (revision 3) exited 0; `kyl_migrate_role_exists`,
  `kyl_app_role_exists`, `vector_extension_present`,
  `kyl_migrate_can_create_in_schema`, and `kyl_app_cannot_create_in_schema` all
  logged `PASS`; no password or connection string appears in the log.
- Both bootstrap-only IAM roles deleted immediately after; re-verified via
  `simulate-principal-policy` that none of the five long-lived project roles
  can read the RDS master secret.
- `simulate-principal-policy`, 9 cases: `kyl-api-execution`/`kyl-worker-execution`
  can read `database-url-app`; only `kyl-migration-execution` can read
  `database-url-migrate`; cross-reads and Voyage/Gemini reads by the migration
  role all evaluate `implicitDeny` -- all 9 matched intent with zero policy
  edits needed (the Phase 6C name-prefix ARN design worked as intended).
- Migration task exited 0; log shows all six migrations running from empty to
  `20260904_0006`. A second one-off run using the same task definition with a
  `containerOverrides` command swap (`--verify`, no new registration needed)
  exited 0 with 22/22 checks `PASS`: `vector` present; `users`, `documents`,
  `document_chunks`, `grounded_answer_cache` all exist; `kyl_app` denied
  `CREATE` on the schema; `kyl_app` granted `SELECT`/`INSERT`/`UPDATE`/`DELETE`
  on all four tables via `has_table_privilege`, proving the `ALTER DEFAULT
  PRIVILEGES` mechanism reached real, post-migration objects.
- Worker service: exactly one task ARN throughout a 5-minute observation window
  (`rolloutState: COMPLETED` from the third check onward), log shows "Ingestion
  worker started" with no restart.
- ALB reached `active` state; target group registered one target that reached
  `healthy`; API service `rolloutState: COMPLETED`, log shows a clean Uvicorn
  startup with the internal ALB health check already returning 200 before any
  external check ran.
- External `GET /health` → `200 {"status":"ok"}`; external `GET /documents`
  (no token) → `401 {"detail":"Not authenticated."}` with a
  `WWW-Authenticate: Bearer` header -- proves the deployed API enforces
  Cognito auth rather than bypassing it.
- HTTP:80 listener deleted; three follow-up requests to the ALB DNS name all
  returned connection failures (`HTTP 000`), confirming port 80 serves no
  application traffic. The ALB, target group, and API service were left
  running per the approved Phase 6D→6E boundary.
- `accountPlanType=FREE`, `accountPlanStatus=ACTIVE`, credits unchanged at
  $120.00, checked both before provisioning began and after every resource
  above was created.

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
Phase 6C.

### Phase 6D incremental cost

Live AWS Price List data for Canada Central: Fargate `$0.04456/vCPU-hour` and
`$0.004865/GB-hour`; ALB `$0.02475/hour` plus `$0.0088/LCU-hour`; public IPv4
`$0.005/hour per address`.

| Item | Daily |
| --- | ---: |
| API Fargate (0.25 vCPU + 1 GiB) | $0.384 |
| Worker Fargate (0.25 vCPU + 1 GiB) | $0.384 |
| 2 task public IPv4 addresses | $0.240 |
| ALB hours (no listener attached; LCU usage ≈ $0) | $0.594 |
| 2 ALB public IPv4 addresses (one per AZ) | $0.240 |
| ECR storage (3 image tags, ~450 MB combined) | ~$0.002 |
| 2 new secrets (`database-url-app`, `database-url-migrate`) | $0.026 |
| **Phase 6D total** | **≈ $1.87** |
| Phase 6B + 6C total (unchanged) | $16.94 |
| **Running total** | **≈ $18.81/month, ≈ $2.51/day** |

Actual payable amount was confirmed at **$0** immediately before provisioning
began and again after every resource above was created and verified; the
account remained `FREE`/`ACTIVE` with the full $120.00 credit balance
unaffected throughout (usage draws down credit, not the payment method). The
ALB is the single largest new line item at ~$0.83/day combined (hours + its two
IPs) -- deleting it, rather than only its listener, would be the next lever if
cost needs to drop further before Phase 6E.
