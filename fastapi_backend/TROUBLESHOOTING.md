# Troubleshooting Database Connectivity

This backend uses SQLAlchemy with PostgreSQL (Supabase). It supports:
- DATABASE_URL (preferred)
- SUPABASE_DB_CONNECTION_STRING (legacy fallback)
- Discrete env vars: user, password, host, port, dbname (composed automatically)

Health endpoints `/` and `/health` never touch the database. Use them for readiness checks even if DB is unreachable. `/health/db` intentionally tests DB connectivity.

## Common Issues

1) psycopg2 OperationalError: "could not connect to server ... Network is unreachable"
- Likely wrong host/port, blocked egress, or DB not accessible from your environment.
- For Supabase, verify the direct connection host and port and that egress is allowed.
- Ensure you are using port 5432 (standard Postgres). The application no longer supports 6543.

2) Import or startup fails due to DB URL missing
- This project initializes the engine lazily; app should still start.
- If you call any /data, /nlq, or /health/db endpoint without a configured DB, you’ll get an explicit 503/500.

## Verify Startup Without DB

From fastapi_backend:
```
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Leave DB values empty to skip DB
python scripts/verify_startup.py
```

You should see:
- FastAPI starts
- GET /health returns 200 {"status":"ok"}

You can also check:
```
curl -s http://127.0.0.1:3001/health
curl -s http://127.0.0.1:3001/debug/config
```

## Configure Database

Option A: Single URL (recommended)
- Edit .env:
```
DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST:PORT/DBNAME?sslmode=require"
```
- The app will ensure psycopg2 scheme and sslmode=require if missing.

Option B: Discrete parts
- Edit .env:
```
user="USER"
password="PASS"
host="HOST"
port="6543"   # or 5432 depending on your environment
dbname="postgres"
```
- The app will compose the URL with sslmode=require.

Option C: Legacy URL
- Set SUPABASE_DB_CONNECTION_STRING if DATABASE_URL is empty.

Optional for previews:
- Set DISABLE_DB_POOL=true to avoid stale pooled connections.

## Test DB Connectivity

Once configured, call:
```
curl -s http://127.0.0.1:3001/health/db
```
- 200 {"status":"ok"} => DB reachable
- 503 with details => check `debug/config` for redacted URL and env precedence.

## Supabase HTTP Client

To use Supabase via HTTP (no direct DB port):
- Set in .env:
```
ENABLE_SUPABASE="true"
SUPABASE_URL="https://<project>.supabase.co"
SUPABASE_ANON_KEY="<anon key>"
SUPABASE_TEST_TABLE="items"   # optional
```
- Ping:
```
curl -s "http://127.0.0.1:3001/supabase/ping?table=items"
```
This path never uses psycopg2 or direct Postgres networking.

## Debugging Tips

- GET /debug/config shows which source is active (DATABASE_URL, legacy, or discrete) and a redacted URL.
- Ensure only one source is set to avoid precedence confusion. DATABASE_URL wins over legacy.
- If your environment restricts outbound connections on 5432, use the correct proxy port (often 6543) or rely on Supabase HTTP endpoints.

## Still Failing?

- Verify credentials and networking to your Supabase Postgres host.
- Try DISABLE_DB_POOL=true in ephemeral environments.
- Check logs for “SQLAlchemy engine initialized” details.
- Use a psql client from the same environment to confirm reachability to HOST:PORT.
