# ReFind database migrations

Use Alembic for a new deployment or a reviewed PostgreSQL migration:

```powershell
$env:REFIND_DATABASE_URL = "postgresql+psycopg://user:password@host:5432/refind"
alembic upgrade head
alembic current
```

For a local isolated schema check:

```powershell
$env:REFIND_DATABASE_URL = "sqlite:///backend/migration-check.db"
alembic upgrade head
alembic downgrade base
```

The existing `backend/refind.db` is preserved. Do not point destructive
migration tests at the user database.

To run the non-destructive PostgreSQL runtime smoke test, set the URL through
the environment and opt in explicitly:

```powershell
$env:REFIND_RUN_POSTGRES_TESTS = "1"
python -m pytest -q backend/test_postgres.py
```

The test creates uniquely named records and does not truncate or reset tables.
It is skipped unless both the opt-in flag and a PostgreSQL URL are present.
