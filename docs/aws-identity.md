# AWS Identity: Deployment, Execution, and Application Users

This is the identity runbook for the temporary Know Your Lease AWS deployment. It
covers who or what can act as whom, why, and how to verify it independently. It
never contains secret values -- see [aws-resource-inventory.md](aws-resource-inventory.md)
for resource identifiers and [aws-deployment.md](aws-deployment.md) for the
workload configuration those identities support.

## The four identity layers

| Layer | Identity | Credential | Purpose |
| --- | --- | --- | --- |
| Human deployment | `kyl-deployer` (IAM user) | Access key, profile `kyl-deploy` | Creates/manages AWS resources for this project |
| Root (break-glass only) | account root | Console password (no access keys) | Emergency/account-level actions only; not used routinely |
| ECS execution | 3 roles (`kyl-*-execution`) | Assumed by the ECS agent | Pull the image, write logs, fetch that workload's secrets |
| ECS application | 2 roles (`kyl-*-task`) | Assumed by the running container | The app's own S3/SQS calls |
| End users | Cognito pool users | JWT access token | Application sign-in; never touches AWS IAM |

These are deliberately kept separate. A Cognito end user can never reach AWS
APIs. An ECS task role can never manage IAM, Cognito, or Secrets Manager
metadata. `kyl-deployer` can manage those, but cannot read any application
secret's *value*, cannot create new IAM users or access keys, and is explicitly
denied the two account-level actions this project must never touch.

## Non-root deployment identity: `kyl-deployer`

### Why root was being used, and why that had to stop

The AWS CLI was authenticated as `arn:aws:iam::297784246437:root` before Phase
6C. Inspection at the start of this phase established two things that changed
the shape of the fix:

- `AccountAccessKeysPresent = 0` -- **no root access keys ever existed.** There
  was nothing to rotate or delete.
- `~/.aws/config` contained `login_session = arn:aws:iam::297784246437:root` --
  this was AWS CLI v2's `aws login`, a browser-based console sign-in that mints
  temporary, auto-refreshing credentials. Not a static secret on disk.

So the actual problem was narrower than "root keys must be rotated": it was
"routine work is authenticated as the root **principal**," which matters
regardless of whether the credential behind it is a long-lived key or a
refreshing session. Root has no permission boundary; every action it takes is
unauditable against a scoped policy.

### What was created

- IAM user `kyl-deployer`, no `AdministratorAccess`, no console access used
  routinely (a login profile exists with `PasswordResetRequired=true`, created
  for a possible future browser-based session, but was never used to sign in
  this session).
- Customer-managed policy `KnowYourLeaseDeployerPolicy`, attached to
  `kyl-deployer` only.
- One access key for `kyl-deployer`, configured into the `kyl-deploy` named CLI
  profile via `aws configure set` (never printed, never written to any file
  this repository tracks).

### Why an access key instead of `aws login` for the IAM user

The plan's preferred path was `aws login --profile kyl-deploy` -- a temporary,
auto-refreshing session credential, with no static secret ever touching disk.
It was tested, not assumed:

```
$ aws login --profile kyl-deploy
Attempting to open your default browser. If the browser does not open, open the following URL.
https://ca-central-1.signin.aws.amazon.com/v1/authorize?response_type=code&client_id=...
```

This command opens a real browser and requires a human to sign in interactively
(including completing the forced password reset on `kyl-deployer`'s login
profile). The automated session performing this deployment has no browser and
cannot complete that flow. This is an environmental limitation, not evidence
that `aws login` is incompatible with IAM users -- a human running the same
command in a normal terminal would likely complete it fine, and that path
remains available to you later if you want a keyless session.

Per the approved fallback, an access key was created instead:

```bash
aws iam create-access-key --user-name kyl-deployer --output json > <restricted-temp-file>
# parsed directly into `aws configure set` calls; temp file deleted immediately after
```

The secret value was redirected straight from the AWS CLI into a file with
`chmod 600`, read once by a script that called `aws configure set
aws_access_key_id/aws_secret_access_key --profile kyl-deploy`, and the temp file
was deleted immediately after. The value was never printed to a terminal, never
included in a report, and never committed.

### The gate that was proven before continuing

```bash
$ aws sts get-caller-identity --profile kyl-deploy
{
    "UserId": "AIDAUKVKTACSRSZJVDQA6",
    "Account": "297784246437",
    "Arn": "arn:aws:iam::297784246437:user/kyl-deployer"
}
```

The `UserId` prefix `AIDA...` and the `user/kyl-deployer` ARN are the tell: root
would return the bare account ID as `UserId` and `:root` as the ARN. Every AWS
resource created after this point in Phase 6C used the `kyl-deploy` profile.
Root was used exactly once more, for a single read-only
`organizations:DescribeOrganization` call, because `kyl-deployer`'s own policy
denies *all* `organizations:*` actions -- including reads -- as a deliberate
guardrail (see below). That one call mutated nothing.

### `KnowYourLeaseDeployerPolicy`: what it allows and explicitly denies

Full policy: `aws iam get-policy-version --policy-arn arn:aws:iam::297784246437:policy/KnowYourLeaseDeployerPolicy --version-id v2`
(current default; `v1` is the Phase 6C version, retained for history). Summary
below covers `v1`'s statements first; the **Phase 6D additions** subsection
covers what `v2` added on top.

**Allowed**, scoped to this project's resources or to safe read-only actions:
- Read-only account/cost checks: `sts:GetCallerIdentity`, `freetier:Get*`,
  `organizations:DescribeOrganization`, `pricing:Get*`, `account:GetAccountInformation`.
- Read-only infrastructure visibility: `Describe*`/`List*`/`Get*` across EC2,
  RDS, SQS, ECS, CloudWatch Logs, and IAM (including
  `iam:SimulatePrincipalPolicy`, used throughout this phase to prove the task
  roles behave as intended before trusting them).
- S3 bucket *configuration* visibility (not object data) on the one project
  bucket.
- IAM role/policy management, scoped by name: `role/kyl-*` and
  `policy/KnowYourLease*` only. `iam:PassRole` is further restricted to
  `role/kyl-*` and only when `iam:PassedToService = ecs-tasks.amazonaws.com`.
- ECR management scoped to the `know-your-lease-backend` repository ARN, plus
  the account-wide `ecr:GetAuthorizationToken` (this action has no
  resource-level permission type).
- Secrets Manager `Create`/`Describe`/`Put`/`Update`/`Delete`/`Tag` scoped to
  the `know-your-lease/prod/*` name prefix. **`secretsmanager:GetSecretValue` is
  deliberately not granted** -- the deployer writes secret values from local
  files it already has; it never needs to read one back to prove it exists.
- `cognito-idp:*` on all resources. Cognito has no other footprint in this
  account, so resource-level scoping before a pool exists isn't practical; the
  Free-plan/paid-tier guardrail here is a parameter choice at creation time
  (`--user-pool-tier LITE`), not something IAM can express as a permission.

**Explicitly denied**, and each one verified with `iam:SimulatePrincipalPolicy`:
- `freetier:UpgradeAccountPlan` -- the account must never leave the Free plan.
- `organizations:*` -- joining an Organization is one of the documented
  Free-plan auto-upgrade risks.
- `account:PutAccountName`, `account:StartPrimaryEmailUpdate`,
  `account:AcceptPrimaryEmailUpdate`, `aws-marketplace:Subscribe`,
  `aws-marketplace:AcceptAgreementRequest` -- account-identity and paid
  Marketplace mutation.
- `iam:CreateUser`, `iam:CreateAccessKey`, `iam:CreateLoginProfile`,
  `iam:UpdateLoginProfile`, `iam:AttachUserPolicy`, `iam:PutUserPolicy`,
  `iam:CreateGroup`, `iam:AttachGroupPolicy`, `iam:PutGroupPolicy` -- the
  deployer manages *roles* for ECS workloads; it cannot create new human/service
  identities or grant itself broader user-level permissions. This closes an
  escalation path that a purely role-scoped policy would otherwise leave open.
- A self-lockout guard scoped to `kyl-deployer`'s own user ARN:
  `iam:DeleteUser`, `iam:DeleteLoginProfile`, `iam:DeactivateMFADevice`,
  `iam:DeleteVirtualMFADevice`, `iam:DeleteAccessKey`, `iam:DetachUserPolicy`,
  `iam:DeleteUserPolicy`, `iam:PutUserPolicy` against itself. This does not
  block a human (or root) from fixing `kyl-deployer` through the console; it
  blocks `kyl-deployer` from doing these things to itself, accidentally or
  otherwise.

### Phase 6D additions (`v2`)

All 15 `v1` statements above, including all 5 Deny statements, carry forward
into `v2` byte-for-byte -- verified programmatically before publishing by
comparing each preserved statement's JSON, not just eyeballing a diff.
Added on top, all newly **allowed**:

- ECR image-push actions (`InitiateLayerUpload`, `UploadLayerPart`,
  `CompleteLayerUpload`, `PutImage`, `BatchCheckLayerAvailability`,
  `BatchGetImage`, `GetDownloadUrlForLayer`), scoped to the
  `know-your-lease-backend` repository ARN.
- `ecs:CreateCluster`/`DeleteCluster`/`RegisterTaskDefinition`/
  `DeregisterTaskDefinition`/`TagResource` on `Resource: "*"` -- AWS does not
  support resource-level permissions for cluster creation or task-definition
  registration (the ARN doesn't exist until the call succeeds), so these
  cannot be scoped further.
- `ecs:RunTask`/`StopTask`/`CreateService`/`UpdateService`/`DeleteService`,
  scoped to `know-your-lease-*` task-definition/service/task ARNs **and**
  gated by an `ecs:cluster` condition matching only
  `know-your-lease-prod` -- unlike the actions above, these do support
  resource-level scoping, so they get it.
- CloudWatch Logs group management (`CreateLogGroup`, `PutRetentionPolicy`,
  `DeleteLogGroup`, `GetLogEvents`, `FilterLogEvents`), scoped to
  `/ecs/know-your-lease/*`. `logs:TagResource` was cut for policy-size reasons
  (see `docs/aws-deployment.md`'s Phase 6D deviations); log groups in this
  phase were created without inline tags as a direct consequence.
- ELBv2 management (create/delete load balancer, target group, listener;
  register/deregister targets; modify attributes; security groups; tags) plus
  `Describe*`, on `Resource: "*"` -- load-balancer and target-group ARNs don't
  exist before creation, and `Describe*` calls are inherently account-wide.
- `iam:CreateServiceLinkedRole`, gated by an `iam:AWSServiceName` condition
  matching only `ecs.amazonaws.com` and `elasticloadbalancing.amazonaws.com` --
  a condition-based restriction rather than a resource-based one, since the
  service-linked role's exact name is chosen by AWS, not the caller.

No `s3:*`, `sqs:*`, `secretsmanager:*`, `ec2:CreateNetworkInterface`, or
`AdministratorAccess` was added. The deployer still cannot read any secret
*value* (`secretsmanager:GetSecretValue` remains ungranted) and still cannot
create a new IAM user, access key, or login profile.

### The temporary bootstrap identities (created and deleted within Phase 6D)

`kyl-bootstrap-execution` and `kyl-bootstrap-task` existed only for the
duration of the one-off database-role bootstrap task and were deleted
immediately after it succeeded -- they are not part of the standing identity
set above and do not appear in `KnowYourLeaseDeployerPolicy` at all (they were
their own separate roles). The execution role carried only the AWS-managed
ECS execution baseline (no Secrets Manager access -- the master secret's ARN
travelled as plain task configuration, not as an ECS `secrets` injection, so
the *execution* role never needed to touch it). The task role could read only
the RDS-managed master secret and create/update only
`know-your-lease/prod/database-url-*`. After deletion,
`simulate-principal-policy` was re-run against all five long-lived project
roles to confirm none of them can read the RDS master secret -- this is the
proof that the bootstrap privilege did not quietly become permanent.

## Root: break-glass only

- Root has **no access keys** (`AccountAccessKeysPresent = 0`), and none were
  created during this phase.
- Root has **no MFA enabled** (`AccountMFAEnabled = 0`) as of the end of this
  phase. **This requires you personally, with an authenticator app; it cannot
  be completed by an automated session.** See the instructions immediately
  below.
- Root retains full console access and is never disabled. It is the only
  identity that can delete `kyl-deployer` (a role cannot delete the user
  granting its own permissions in a way that's safe to automate) and the only
  identity Cognito/IAM/ECR could not manage before `kyl-deployer` existed.
- After this phase, root should not be used for routine work. Use it only for:
  break-glass account recovery, actions IAM itself cannot grant (rare), or the
  final step of tearing down `kyl-deployer` itself.

### Manual step: enable root MFA

1. Sign in to the [AWS Console](https://console.aws.amazon.com/) as the root
   user (your account email + root password).
2. Open **IAM** → **Dashboard**, or go directly to **My Security Credentials**
   from the account menu (top right).
3. Under **Multi-factor authentication (MFA)**, choose **Assign MFA device**.
4. Select **Authenticator app**, name it (e.g. "root-authenticator"), and scan
   the QR code with an authenticator app (Google Authenticator, Authy, 1Password,
   etc.).
5. Enter two consecutive codes from the app to confirm.

After you complete this, verification is:

```bash
aws iam get-account-summary --profile kyl-deploy --output json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['SummaryMap']['AccountMFAEnabled'])"
# expect: 1
```

## ECS execution roles vs. application task roles

These are the most commonly confused pair in ECS, so it's worth stating plainly:

- **Execution role** (`kyl-api-execution`, `kyl-worker-execution`,
  `kyl-migration-execution`): assumed by the **ECS agent itself**, before your
  code runs. It pulls the container image from ECR, writes container stdout/
  stderr to CloudWatch Logs, and resolves the Secrets Manager values referenced
  in the task definition's `secrets` block into environment variables. Your
  application code never directly uses this role's credentials.
- **Task role** (`kyl-api-task`, `kyl-worker-task`): assumed by **your running
  container**, available to it via the ECS credential endpoint exactly like an
  EC2 instance profile. This is what `boto3` picks up automatically when the
  application calls S3 or SQS -- no access key, no secret key, ever, inside the
  container.

The migration workload has no task role because `alembic upgrade head` makes no
AWS API calls of its own -- it only needs its execution role to fetch
`DATABASE_URL` and to log its output.

Three execution roles (rather than one shared role) exist because the secret
sets they can read genuinely differ in privilege: the worker must never be able
to read the Gemini key, and neither the API nor the worker should be able to
read the schema-owning migration database credential once it exists in Phase
6D. A shared execution role would erase that boundary.

## Cognito application users vs. IAM identities

These are unrelated identity systems that happen to live in the same AWS
account, and Know Your Lease keeps them that way on purpose:

- **Cognito user pool users** (`know-your-lease-prod`,
  `ca-central-1_Lhw9u8Yh6`) are end users of the *application* -- people signing
  up to ask questions about their lease. They authenticate via the Hosted UI,
  receive a JWT access token, and that token is meaningful only to the FastAPI
  backend (`backend/app/core/auth.py` verifies it against Cognito's JWKS). A
  Cognito user has no AWS permissions of any kind and cannot call any AWS API.
- **IAM identities** (`kyl-deployer`, the five ECS roles) are AWS-account
  principals that can call AWS APIs. No IAM identity in this project can sign
  in as a Cognito application user, and no Cognito user can assume an IAM role.

## Verifying this identity setup independently

```bash
# Confirm routine CLI identity is non-root
aws sts get-caller-identity --profile kyl-deploy

# Confirm root has no access keys and (once you've completed it) has MFA
aws iam get-account-summary --profile kyl-deploy --output json

# Confirm the Free-plan guardrails are real, not just written down
aws iam simulate-principal-policy --profile kyl-deploy \
  --policy-source-arn arn:aws:iam::297784246437:user/kyl-deployer \
  --action-names freetier:UpgradeAccountPlan organizations:CreateOrganization iam:CreateUser

# Confirm the account is still Free/Active
aws freetier get-account-plan-state --region us-east-1 --profile kyl-deploy
```

## Teardown

See [aws-resource-inventory.md](aws-resource-inventory.md#required-teardown-order-phase-6c-before-phase-6b)
for the exact dependency-ordered commands. In summary: task roles, then
execution roles, then secrets (force-deleted to avoid recovery-window billing),
then ECR, then Cognito domain → client → pool, and `kyl-deployer` itself
**last**, using root for that final step since `kyl-deployer` cannot delete
itself.
