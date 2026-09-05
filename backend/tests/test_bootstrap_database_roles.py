from unittest.mock import MagicMock, patch

import pytest

from app.bootstrap.create_database_roles import (
    APP_ROLE,
    MIGRATE_ROLE,
    build_database_url,
    check_schema_level_privileges,
    create_or_reset_role,
    generate_password,
    main,
    normalize_conninfo,
    role_exists,
    run_verify,
)


class FakeCursor:
    """Records every execute() call and returns queued fetchone/fetchall values
    in call order, so tests can assert on exact SQL shape without a real DB."""

    def __init__(self, fetchone_queue=None, fetchall_queue=None):
        self.executed: list[tuple] = []
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_queue = list(fetchall_queue or [])

    def execute(self, query, params=None):
        self.executed.append((str(query), params))

    def fetchone(self):
        return self._fetchone_queue.pop(0) if self._fetchone_queue else None

    def fetchall(self):
        return self._fetchall_queue.pop(0) if self._fetchall_queue else []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_generate_password_is_long_and_url_safe() -> None:
    password = generate_password()
    assert len(password) >= 32
    assert all(c.isalnum() or c in "-_" for c in password)


def test_generate_password_is_random_each_call() -> None:
    assert generate_password() != generate_password()


def test_build_database_url_uses_ssl_and_psycopg_dialect() -> None:
    url = build_database_url(username="kyl_app", password="secret", host="db.example", port=5432, dbname="leases")

    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url
    assert "kyl_app" in url
    assert "db.example:5432" in url
    assert "/leases" in url


def test_build_database_url_percent_encodes_special_characters() -> None:
    url = build_database_url(username="kyl_app", password="p@ss/word?#", host="h", port=5432, dbname="d")

    assert "p@ss/word?#" not in url
    assert "%40" in url  # @
    assert "%2F" in url  # /


def test_normalize_conninfo_strips_sqlalchemy_dialect_suffix() -> None:
    sqlalchemy_style = "postgresql+psycopg://user:pw@host:5432/db?sslmode=require"

    assert normalize_conninfo(sqlalchemy_style) == "postgresql://user:pw@host:5432/db?sslmode=require"


def test_normalize_conninfo_is_a_noop_for_plain_urls() -> None:
    plain = "postgresql://user:pw@host:5432/db"

    assert normalize_conninfo(plain) == plain


def test_role_exists_true_when_row_returned() -> None:
    cursor = FakeCursor(fetchone_queue=[(1,)])

    assert role_exists(cursor, "kyl_app") is True
    assert cursor.executed[0][1] == ("kyl_app",)


def test_role_exists_false_when_no_row() -> None:
    cursor = FakeCursor(fetchone_queue=[None])

    assert role_exists(cursor, "kyl_app") is False


def test_create_or_reset_role_creates_when_absent() -> None:
    cursor = FakeCursor(fetchone_queue=[None])

    create_or_reset_role(cursor, "kyl_app", "hunter2")

    create_query, params = cursor.executed[-1]
    # PostgreSQL's role DDL rejects a bind parameter for PASSWORD, so the value
    # must travel as a properly escaped sql.Literal inside the composed query,
    # not as a separate execute() parameter.
    assert params is None
    assert "SQL('CREATE ROLE '" in create_query
    assert "Literal('hunter2')" in create_query


def test_create_or_reset_role_alters_when_present() -> None:
    cursor = FakeCursor(fetchone_queue=[(1,)])

    create_or_reset_role(cursor, "kyl_app", "hunter2")

    alter_query, params = cursor.executed[-1]
    assert params is None
    assert "SQL('ALTER ROLE '" in alter_query
    assert "Literal('hunter2')" in alter_query


def test_check_schema_level_privileges_all_pass() -> None:
    cursor = FakeCursor(
        fetchall_queue=[[(MIGRATE_ROLE,), (APP_ROLE,)]],
        fetchone_queue=[(1,), (True,), (False,)],  # vector present, migrate can create, app cannot
    )

    result = check_schema_level_privileges(cursor)

    assert result == {
        "kyl_migrate_role_exists": True,
        "kyl_app_role_exists": True,
        "vector_extension_present": True,
        "kyl_migrate_can_create_in_schema": True,
        "kyl_app_cannot_create_in_schema": True,
    }


def test_check_schema_level_privileges_detects_app_role_with_unwanted_create() -> None:
    cursor = FakeCursor(
        fetchall_queue=[[(MIGRATE_ROLE,), (APP_ROLE,)]],
        fetchone_queue=[(1,), (True,), (True,)],  # app CAN create -- must fail the check
    )

    result = check_schema_level_privileges(cursor)

    assert result["kyl_app_cannot_create_in_schema"] is False


def test_check_schema_level_privileges_detects_missing_role() -> None:
    cursor = FakeCursor(
        fetchall_queue=[[(MIGRATE_ROLE,)]],  # kyl_app missing entirely
        fetchone_queue=[None, (True,), (False,)],
    )

    result = check_schema_level_privileges(cursor)

    assert result["kyl_app_role_exists"] is False


def test_run_verify_passes_when_all_checks_true() -> None:
    fake_conn = MagicMock()
    fake_cursor = FakeCursor(
        fetchone_queue=[(1,)]  # vector extension present
        + [(False,)]  # app cannot create in schema -- correct
        + [(True,)] * (4 * 4),  # 4 tables x 4 privileges, all granted
    )
    # information_schema.tables query returns all four expected tables
    fake_cursor._fetchall_queue = [
        [("users",), ("documents",), ("document_chunks",), ("grounded_answer_cache",)]
    ]
    fake_conn.cursor.return_value = fake_cursor
    fake_conn.close = MagicMock()

    with patch("app.bootstrap.create_database_roles.psycopg.connect", return_value=fake_conn):
        assert run_verify("postgresql+psycopg://kyl_migrate:pw@host:5432/db") is True
    fake_conn.close.assert_called_once()


def test_run_verify_fails_when_a_table_is_missing() -> None:
    fake_conn = MagicMock()
    fake_cursor = FakeCursor(
        fetchone_queue=[(1,), (False,)] + [(True,)] * (2 * 4)  # only 2 tables found, both fully granted
    )
    fake_cursor._fetchall_queue = [[("users",), ("documents",)]]  # missing two required tables
    fake_conn.cursor.return_value = fake_cursor

    with patch("app.bootstrap.create_database_roles.psycopg.connect", return_value=fake_conn):
        assert run_verify("postgresql+psycopg://kyl_migrate:pw@host:5432/db") is False


def test_main_requires_database_url_for_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["--verify"]) == 1


def test_main_requires_master_secret_arn_to_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RDS_MASTER_SECRET_ARN", raising=False)
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_NAME", "know_your_lease")

    assert main([]) == 1


def test_main_requires_db_host_and_name_to_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDS_MASTER_SECRET_ARN", "arn:aws:secretsmanager:ca-central-1:1:secret:x")
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    assert main([]) == 1


def test_main_verify_mode_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://kyl_migrate:pw@host:5432/db")

    with patch("app.bootstrap.create_database_roles.run_verify", return_value=True) as mocked:
        assert main(["--verify"]) == 0
    mocked.assert_called_once_with("postgresql+psycopg://kyl_migrate:pw@host:5432/db")


def test_main_bootstrap_mode_returns_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDS_MASTER_SECRET_ARN", "arn:aws:secretsmanager:ca-central-1:1:secret:x")
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_NAME", "know_your_lease")

    with patch("app.bootstrap.create_database_roles.run_bootstrap", return_value=False):
        assert main([]) == 1


def test_main_bootstrap_mode_defaults_port_to_5432(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RDS_MASTER_SECRET_ARN", "arn:aws:secretsmanager:ca-central-1:1:secret:x")
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_NAME", "know_your_lease")
    monkeypatch.delenv("DB_PORT", raising=False)

    with patch("app.bootstrap.create_database_roles.run_bootstrap", return_value=True) as mocked:
        assert main([]) == 0
    mocked.assert_called_once_with(
        "arn:aws:secretsmanager:ca-central-1:1:secret:x", host="db.example", port=5432, dbname="know_your_lease"
    )
