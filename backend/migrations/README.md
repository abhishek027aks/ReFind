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
