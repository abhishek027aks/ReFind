# ReFind Project Guide

## What is included

- Student registration and login with PBKDF2 password hashing.
- Admin role login and protected dashboard data.
- Lost and found item reports with search and category filtering.
- Automatic, explainable text-based matching between opposite report types.
- Private ownership claims, return-point selection, and report-state tracking.
- Persistent SQLite or PostgreSQL tables for users, reports, claims, matches, and notifications.
- Configurable upload and database paths through environment variables.
- Image content-signature validation for JPG, PNG, and WebP uploads.
- Ownership checks prevent users from claiming their own report or duplicating an active claim.

## Report lifecycle

`open -> possible_match -> claimed -> verified -> returned -> closed`

An administrator can also flag a suspicious report. Public report views never expose account email addresses, ownership answers, or private contact information.

## API groups

| Group | Purpose |
| --- | --- |
| `/auth` | Register, login, and inspect the active account |
| `/reports` | Browse public reports and create owned reports |
| `/claims` | Submit a private ownership claim |
| `/matches` | View relevant automated matches |
| `/notifications` | View and acknowledge account notifications |
| `/admin` | Admin-only statistics, claims, and report moderation |

## Production checklist

1. Set a unique `REFIND_TOKEN_SECRET` before deployment.
2. Set `REFIND_CORS_ORIGINS` to the exact HTTPS frontend origins.
3. Replace the seeded demo admin password and use HTTPS-only cookies or a secure token store.
4. Set `REFIND_DATABASE_URL` to the Supabase Session Pooler URL and run `alembic upgrade head`; the API selects the PostgreSQL SQLAlchemy adapter automatically.
5. Add email/college-SIS verification and rate limiting at the reverse proxy or API gateway.
6. Replace simple token-overlap matching with reviewed embedding/image signals; never treat a match score as proof of ownership.

`REFIND_STORAGE_PROVIDER=s3` enables object storage through the AWS-compatible
S3 API. The API validates the bucket configuration and never accepts a client
path as a storage filename. `REFIND_REDIS_URL` enables a shared Redis limiter;
without it, the fallback is process-local and must not be used behind multiple
API replicas.

## Validation commands

```powershell
npm run build
cd backend
python -m compileall -q main.py
python -m pytest -q test_api.py
```

## Container deployment

`Dockerfile` runs the API with a persistent data directory and
`docker-compose.yml` starts the API and Vite frontend together. The compose
volume contains the local SQLite database and uploaded images; back it up before
recreating the volume. For PostgreSQL deployment, run migrations against the
Supabase database first and supply the URL only through the environment. The
explicit `backend/import_sqlite_to_postgres.py` script performs additive,
conflict-safe import if existing local data must be transferred.
