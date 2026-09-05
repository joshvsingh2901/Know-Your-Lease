"""One-off PostgreSQL role bootstrap for the private RDS instance.

Run exactly once, from inside the VPC, using the RDS-managed master secret. It
creates two application roles (`kyl_migrate`, the schema owner Alembic runs as;
`kyl_app`, runtime-only DML access with no DDL) and writes their connection
strings to Secrets Manager. The master credential is used here and nowhere else
in the running system.

    python -m app.bootstrap.create_database_roles            # create/reset roles + secrets
    python -m app.bootstrap.create_database_roles --verify   # read-only check via DATABASE_URL

Never logs a password, a connection string containing one, or the master
secret's contents. Only role names, secret names, and pass/fail booleans are
logged.
"""

import argparse
import json
import logging
import os
import secrets as secrets_module
from urllib.parse import quote

import boto3
import psycopg
from psycopg import sql

logger = logging.getLogger(__name__)

MIGRATE_ROLE = "kyl_migrate"
APP_ROLE = "kyl_app"

APP_SECRET_NAME = "know-your-lease/prod/database-url-app"
MIGRATE_SECRET_NAME = "know-your-lease/prod/database-url-migrate"

REQUIRED_TABLES = ("users", "documents", "document_chunks", "grounded_answer_cache")


def _aws_region() -> str:
    return os.environ.get("AWS_REGION", "ca-central-1")


def _secrets_client():
    return boto3.client("secretsmanager", region_name=_aws_region())


def generate_password() -> str:
    """32 bytes of URL-safe randomness: contains only [A-Za-z0-9_-], so it never
    needs percent-encoding in a connection string userinfo component."""
    return secrets_module.token_urlsafe(32)


def build_database_url(*, username: str, password: str, host: str, port: int, dbname: str) -> str:
    return (
        f"postgresql+psycopg://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{dbname}?sslmode=require"
    )


def normalize_conninfo(database_url: str) -> str:
    """psycopg.connect() accepts a plain postgresql:// URI, not SQLAlchemy's
    +psycopg dialect suffix."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def fetch_master_credentials(secret_arn: str) -> dict:
    """The RDS-managed master secret contains only `username`/`password` --
    the endpoint is not a secret and is not stored in it."""
    response = _secrets_client().get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def connect_as_master(credentials: dict, *, host: str, port: int, dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=credentials["username"],
        password=credentials["password"],
        sslmode="require",
        autocommit=True,
    )


def role_exists(cursor, role_name: str) -> bool:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
    return cursor.fetchone() is not None


def create_or_reset_role(cursor, role_name: str, password: str) -> None:
    """Idempotent: creates the role if absent, otherwise resets its password so
    a re-run always ends with roles matching the newly generated credentials.

    PostgreSQL's role DDL does not accept a query bind parameter for PASSWORD --
    it requires a literal. `sql.Literal` quotes/escapes the value safely into
    the statement text without exposing it to the injection risk a raw f-string
    would carry."""
    if role_exists(cursor, role_name):
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role_name), sql.Literal(password)
            )
        )
        logger.info("Reset password for existing role %s", role_name)
    else:
        cursor.execute(
            sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role_name), sql.Literal(password)
            )
        )
        logger.info("Created role %s", role_name)


def bootstrap_privileges(cursor, *, dbname: str, master_user: str) -> None:
    """Idempotent: every statement here is safe to re-run. Order matters --
    default privileges must be set after schema grants and before Alembic runs,
    since they apply only to objects created afterward."""
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

    cursor.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(dbname), sql.Identifier(MIGRATE_ROLE), sql.Identifier(APP_ROLE)
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(MIGRATE_ROLE))
    )
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(APP_ROLE)))
    cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")

    cursor.execute(
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            sql.Identifier(APP_ROLE)
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            sql.Identifier(APP_ROLE)
        )
    )

    # RDS requires the bootstrapping user to hold the target role's membership
    # before it may alter that role's default privileges.
    cursor.execute(
        sql.SQL("GRANT {} TO {}").format(sql.Identifier(MIGRATE_ROLE), sql.Identifier(master_user))
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(sql.Identifier(MIGRATE_ROLE), sql.Identifier(APP_ROLE))
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(sql.Identifier(MIGRATE_ROLE), sql.Identifier(APP_ROLE))
    )


def check_schema_level_privileges(cursor) -> dict[str, bool]:
    """Checks provable without any table existing yet -- used by the bootstrap
    task itself, before Alembic has created anything."""
    cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN (%s, %s)", (MIGRATE_ROLE, APP_ROLE))
    found_roles = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    vector_present = cursor.fetchone() is not None
    cursor.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (MIGRATE_ROLE,))
    migrate_can_create = bool(cursor.fetchone()[0])
    cursor.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (APP_ROLE,))
    app_can_create = bool(cursor.fetchone()[0])

    return {
        "kyl_migrate_role_exists": MIGRATE_ROLE in found_roles,
        "kyl_app_role_exists": APP_ROLE in found_roles,
        "vector_extension_present": vector_present,
        "kyl_migrate_can_create_in_schema": migrate_can_create,
        "kyl_app_cannot_create_in_schema": not app_can_create,
    }


def put_or_update_secret(name: str, value: str) -> None:
    client = _secrets_client()
    try:
        client.create_secret(
            Name=name,
            SecretString=value,
            Tags=[
                {"Key": "Project", "Value": "KnowYourLease"},
                {"Key": "Environment", "Value": "production"},
                {"Key": "TemporaryDeployment", "Value": "true"},
            ],
        )
        logger.info("Created secret %s", name)
    except client.exceptions.ResourceExistsException:
        client.put_secret_value(SecretId=name, SecretString=value)
        logger.info("Updated existing secret %s", name)


def run_bootstrap(master_secret_arn: str, *, host: str, port: int, dbname: str) -> bool:
    credentials = fetch_master_credentials(master_secret_arn)
    conn = connect_as_master(credentials, host=host, port=port, dbname=dbname)
    try:
        master_user = conn.info.user
        app_password = generate_password()
        migrate_password = generate_password()

        with conn.cursor() as cursor:
            create_or_reset_role(cursor, MIGRATE_ROLE, migrate_password)
            create_or_reset_role(cursor, APP_ROLE, app_password)
            bootstrap_privileges(cursor, dbname=dbname, master_user=master_user)
            checks = check_schema_level_privileges(cursor)

        for name, passed in checks.items():
            logger.info("check %-32s %s", name, "PASS" if passed else "FAIL")
        if not all(checks.values()):
            logger.error("Bootstrap privilege verification failed; secrets were not written.")
            return False

        put_or_update_secret(
            APP_SECRET_NAME,
            build_database_url(username=APP_ROLE, password=app_password, host=host, port=port, dbname=dbname),
        )
        put_or_update_secret(
            MIGRATE_SECRET_NAME,
            build_database_url(
                username=MIGRATE_ROLE, password=migrate_password, host=host, port=port, dbname=dbname
            ),
        )
        logger.info("Database bootstrap completed: roles, privileges, and secrets are in place.")
        return True
    finally:
        conn.close()


def run_verify(database_url: str) -> bool:
    """Read-only, run by the migration task using its own DATABASE_URL
    (kyl_migrate) after Alembic has run -- proves the default-privilege grants
    actually reached the real tables, and re-confirms the schema-level deny."""
    conn = psycopg.connect(normalize_conninfo(database_url), sslmode="require")
    try:
        results: dict[str, bool] = {}
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            results["vector_extension_present"] = cursor.fetchone() is not None

            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(%s)",
                (list(REQUIRED_TABLES),),
            )
            found_tables = {row[0] for row in cursor.fetchall()}
            for table in REQUIRED_TABLES:
                results[f"table_{table}_exists"] = table in found_tables

            cursor.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (APP_ROLE,))
            results["kyl_app_cannot_create_in_schema"] = not bool(cursor.fetchone()[0])

            for table in REQUIRED_TABLES:
                if table not in found_tables:
                    continue
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    cursor.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (APP_ROLE, table, privilege),
                    )
                    results[f"kyl_app_{privilege.lower()}_{table}"] = bool(cursor.fetchone()[0])

        for name, passed in results.items():
            logger.info("check %-40s %s", name, "PASS" if passed else "FAIL")
        return all(results.values())
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Bootstrap or verify Know Your Lease database roles.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-only verification via DATABASE_URL instead of bootstrapping via the master secret.",
    )
    args = parser.parse_args(argv)

    if args.verify:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL is required for --verify.")
            return 1
        return 0 if run_verify(database_url) else 1

    master_secret_arn = os.environ.get("RDS_MASTER_SECRET_ARN")
    db_host = os.environ.get("DB_HOST")
    db_name = os.environ.get("DB_NAME")
    if not master_secret_arn or not db_host or not db_name:
        logger.error("RDS_MASTER_SECRET_ARN, DB_HOST, and DB_NAME are all required to bootstrap.")
        return 1
    db_port = int(os.environ.get("DB_PORT", "5432"))
    return 0 if run_bootstrap(master_secret_arn, host=db_host, port=db_port, dbname=db_name) else 1


if __name__ == "__main__":
    raise SystemExit(main())
