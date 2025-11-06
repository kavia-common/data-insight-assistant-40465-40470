# FastAPI Backend

## Overview
This backend is a FastAPI application that provides a pragmatic REST API with:
- Health checks and diagnostics
- CRUD endpoints for SQLAlchemy-backed data under /data (Postgres on Supabase)
- A Natural Language Query (NLQ) endpoint under /nlq/query that deterministically converts simple natural language into filters and options and queries a JSONB-backed table
- Optional Supabase REST client integration (feature-flagged) under /supabase
- Configurable CORS and structured JSON-like logging

The application is designed to operate with a Supabase Postgres database via SQLAlchemy.

## Requirements
- Python 3.10+
- pip (or a compatible package manager)
- A Supabase Postgres connection string (see Environment Configuration)

## Installation
1. Create and activate a virtual environment:
   - macOS/Linux:
     ```
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - Windows (PowerShell):
     ```
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

2. Install dependencies:
   ```
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Environment Configuration
The application uses Pydantic BaseSettings and loads environment variables from a .env file in the fastapi_backend working directory.

An .env.example is provided with all supported keys. Copy it to .env and adjust values for your environment:
```
cp .env.example .env
```

Required database variable:
- DATABASE_URL: Postgres connection string for SQLAlchemy (e.g., postgresql+psycopg2://user:pass@host:6543/postgres)

Alternative configuration (discrete variables):
- If your environment provides discrete credentials, set ALL of the following keys in .env:
  user=<db user>
  password=<db password>
  host=<db host>
  port=<db port>   # Use 6543 (updated from 5432)
  dbname=<db name>
  The application will automatically construct a SQLAlchemy URL using the psycopg2 driver and enforce sslmode=require.
  For ephemeral preview environments where pooled connections may linger, set DISABLE_DB_POOL=true to use NullPool.

Backward-compatibility:
- If DATABASE_URL is not set, the application will fall back to SUPABASE_DB_CONNECTION_STRING (deprecated).
- For either DATABASE_URL or SUPABASE_DB_CONNECTION_STRING, if sslmode is not present, the app will append sslmode=require automatically for psycopg2 URLs.

### Supported Environment Variables
- APP_NAME: Application name for OpenAPI metadata
- APP_ENV: Environment label (e.g., development, staging, production)
- LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
- PORT: Port FastAPI/uvicorn should listen on (defaults to 3001)
- CORS_ALLOWED_ORIGINS: Comma-separated list of allowed origins (or "*" for all)
- SUPABASE_DB_CONNECTION_STRING: Postgres connection string used by SQLAlchemy
- ENABLE_SUPABASE: true/false; feature flag for Supabase REST client integration under /supabase
- SUPABASE_URL: Supabase project URL (required when ENABLE_SUPABASE=true for /supabase)
- SUPABASE_ANON_KEY: Supabase anon key (required when ENABLE_SUPABASE=true for /supabase)
- ENABLE_NLQ: true/false; enables the /nlq endpoints
- ENABLE_NLQ_AI: true/false; placeholder for future AI-augmented NLQ parsing
- OPENAI_API_KEY: Optional key for future AI integrations

## Running the App

### Local Development (uvicorn)
From the fastapi_backend directory:
```
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# Optionally load env
export $(grep -v '^#' .env | xargs) 2>/dev/null || true
# Start on 0.0.0.0:3001 (PORT overrides default)
uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-3001} --reload
```
- The API will be available at http://localhost:3001 by default.
- Interactive docs: http://localhost:3001/docs
- OpenAPI JSON: http://localhost:3001/openapi.json

On Windows (PowerShell), you can rely on the app automatically loading .env. To override just the port:
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
$env:PORT="3001"
uvicorn src.api.main:app --host 0.0.0.0 --port 3001 --reload
```

### Alternative: Python launcher
You can also run using the provided launcher which reads PORT from settings and starts uvicorn:
```
python run.py
```
Hot reload can be enabled by:
```
UVICORN_RELOAD=true python run.py
```

### Start command for container/orchestrator
Ensure the service binds to 0.0.0.0 and port 3001 for readiness:
```
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 3001
# or
python run.py
# or
python main.py
```
Notes:
- The app module path is `src.api.main:app` and the package root is `src/` (it is a Python package with `__init__.py`).
- Always run these commands from the `fastapi_backend` directory so `src` is on the Python path.
- If an orchestrator provides placeholders like <host> or <port>, prefer explicit values:
  host: 0.0.0.0
  port: 3001

### Health readiness
Health and diagnostics endpoints:
- GET / -> {"message":"Healthy"}  (root alias)
- GET /health -> {"status":"ok"} (strictly no-DB; never imports or initializes DB)
- GET /health/healthz -> {"status":"ok"} (alias; strictly no-DB)
- GET /health/db -> {"status":"ok"} (the only endpoint that attempts DB connectivity via SELECT 1)

For readiness checks, probe:
```
curl -sf http://localhost:3001/health >/dev/null
```
Exit code 0 indicates the service is ready.

### Quick verification script
After installing dependencies, you can validate startup and the health endpoint locally:
```
python scripts/verify_startup.py
```
It will:
- Verify FastAPI and Uvicorn imports
- Import `src.api.main:app`
- Start a temporary server on 0.0.0.0:3001 (or PORT) and probe GET /health
- Exit with code 0 if ready

### Preview/Container Run
If your environment provides a preview service (e.g., cloud dev environment), use either `uvicorn` or `python run.py`. Ensure:
- The service exposes the configured PORT (default 3001).
- A .env file is present in the fastapi_backend working directory (copy .env.example).
- The start command uses host 0.0.0.0 and port 3001.

### Troubleshooting startup
- ModuleNotFoundError: fastapi — install deps with `pip install -r requirements.txt` in an active virtualenv.
- ImportError: cannot import src.api.main:app — ensure you run from fastapi_backend directory so that `src` package is on sys.path, or set PYTHONPATH to include this directory.
- Address already in use — another process is listening on 3001; stop it or change PORT.
- Requirements install issues — upgrade pip and retry.

## Generating OpenAPI Spec
A helper script is available to dump the OpenAPI schema into interfaces/openapi.json:
```
python -m src.api.generate_openapi
```
This imports the FastAPI app object and writes the current schema to interfaces/openapi.json.

## Data Model
The service uses a generic items table in Postgres with:
- id: UUID primary key (generated server-side)
- data: JSONB payload
- created_at / updated_at: timestamps

The /data endpoints perform CRUD against this table, supporting simple filtering on data.* keys, sorting, pagination, and optional projection of returned data fields.

## Example Requests

### Health
- Root health (back-compat):
  ```
  curl -s http://localhost:3001/
  ```
  Response:
  ```
  {"message":"Healthy"}
  ```

- Detailed health:
  ```
  curl -s http://localhost:3001/health
  ```
  Response (schema):
  ```
  {"status":"ok"}
  ```

### Data CRUD (/data)
These routes operate against the SQL items table.

- Create:
  ```
  curl -s -X POST http://localhost:3001/data \
    -H "Content-Type: application/json" \
    -d '{"data":{"name":"Alice","age":30,"country":"US"}}'
  ```

- Get by id:
  ```
  curl -s http://localhost:3001/data/<uuid>
  ```

- List (filter, projection, sorting, paging):
  ```
  # Filter: data.country == "US"; fields: data.name,data.age; sort by created_at desc; limit 10; offset 0
  curl -G -s http://localhost:3001/data \
    --data-urlencode 'filter={"data.country":"US"}' \
    --data-urlencode 'fields=data.name,data.age' \
    --data-urlencode 'sort_by=created_at' \
    --data-urlencode 'sort_dir=desc' \
    --data-urlencode 'limit=10' \
    --data-urlencode 'offset=0'
  ```

- Update:
  ```
  curl -s -X PUT http://localhost:3001/data/<uuid> \
    -H "Content-Type: application/json" \
    -d '{"data":{"name":"Alice","age":31}}'
  ```

- Delete:
  ```
  curl -s -X DELETE -i http://localhost:3001/data/<uuid>
  ```

### NLQ (/nlq/query)
NLQ parsing is rule-based and deterministic (e.g., "last 7 days", "field equals X", "sort by field desc", "top N").
It produces filters compatible with the SQL JSONB query layer.

Request:
```
curl -s -X POST http://localhost:3001/nlq/query \
  -H "Content-Type: application/json" \
  -d '{"query":"top 5 customers where data.country equals US sort by data.revenue desc fields data.name,data.revenue"}'
```

Optional structure parameters can override parsed defaults:
```
curl -s -X POST http://localhost:3001/nlq/query \
  -H "Content-Type: application/json" \
  -d '{
        "query": "last 7 days sort by created_at desc",
        "params": {"limit": 20, "offset": 0, "sort_by": "created_at", "sort_dir": "desc", "fields":["_id","created_at","total"]}
      }'
```

Response (schema):
```
{
  "nlq": "<original query>",
  "filter": { ... parsed filter ... },
  "items": [ { "_id": "<uuid>", ... }, ... ],
  "meta": { "total": 100, "limit": 20, "offset": 0 }
}
```

Note: If ENABLE_NLQ=false, the endpoint returns 404.

## Supabase Integration (optional)
- Controlled by ENABLE_SUPABASE.
- When enabled, the system attempts to initialize a Supabase client using SUPABASE_URL and SUPABASE_ANON_KEY.
- New route: POST /supabase/query to query a specified table with optional filters (body), ordering, limit, and offset.

### Example usage
- Basic:
```
curl -s -X POST "http://localhost:3001/supabase/query?table=customers&limit=5"
```

- With ordering:
```
curl -s -X POST "http://localhost:3001/supabase/query?table=orders&order_by=created_at&order_dir=desc&limit=10"
```

- With filters (use interactive docs to add multiple filters, or send a JSON body):
In Swagger UI (http://localhost:3001/docs), expand POST /supabase/query, click "Try it out",
add items under "filters" (request body):
[
  {"column":"country","op":"eq","value":"US"},
  {"column":"name","op":"ilike","value":"%ann%"}
]
Then Execute.

Or via curl:
```
curl -s -X POST "http://localhost:3001/supabase/query?table=customers&limit=5" \
  -H "Content-Type: application/json" \
  -d '[{"column":"country","op":"eq","value":"US"}]'
```

Notes:
- Supported operators: eq, neq, lt, lte, gt, gte, ilike.
- The endpoint returns 404 if ENABLE_SUPABASE=false and 503 if credentials are missing.

## CORS
CORS is configured via the CORS_ALLOWED_ORIGINS environment variable. Provide a comma-separated list of origins or "*" to allow all. The app configures CORSMiddleware accordingly.

## Logging
Logs are emitted in a lightweight JSON-like structure to stdout with fields for timestamp, level, logger name, message, and context. Configure verbosity using LOG_LEVEL.

## Project Layout
- src/api/main.py: FastAPI app initialization and routing
- src/routers: Route modules (/health, /data, /nlq, /supabase)
- src/db/sqlalchemy.py: SQLAlchemy engine/session/Base and FastAPI dependency
- src/models/sql_models.py: SQLAlchemy ORM models (items)
- src/models/schemas.py: Pydantic schemas for requests and responses
- src/services/nlq_service.py: Deterministic NLQ parsing
- src/services/supabase_client.py: Optional Supabase wrapper
- src/api/generate_openapi.py: Utility to generate OpenAPI JSON
- interfaces/openapi.json: OpenAPI schema output (can be generated)
- run.py: Uvicorn launcher that reads PORT from settings
- requirements.txt: Python dependencies
