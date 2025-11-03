# FastAPI Backend

## Overview
This backend is a FastAPI application that provides a pragmatic REST API with:
- Health checks and diagnostics
- CRUD endpoints for MongoDB-backed data under /data
- A Natural Language Query (NLQ) endpoint under /nlq/query that deterministically converts simple natural language into MongoDB filters and options
- Optional Supabase integration (feature-flagged)
- Configurable CORS and structured JSON-like logging

The application is designed to operate with or without a live MongoDB connection. It will start even if the database is not reachable, allowing you to test health and static routes in constrained environments.

## Requirements
- Python 3.10+
- pip (or a compatible package manager)
- Optional: a running MongoDB instance if you want to exercise the /data and /nlq endpoints
- Optional: Supabase project credentials if you enable Supabase features

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

### Supported Environment Variables
- APP_NAME: Application name for OpenAPI metadata
- APP_ENV: Environment label (e.g., development, staging, production)
- LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
- PORT: Port FastAPI/uvicorn should listen on (defaults to 3001)
- CORS_ALLOWED_ORIGINS: Comma-separated list of allowed origins (or "*" for all)
- MONGO_URI: MongoDB connection string (e.g., mongodb://localhost:27017 or mongodb+srv://...)
- MONGO_DB_NAME: MongoDB database name
- MONGO_COLLECTION: Default collection name for /data routes and default NLQ target
- MONGO_PING_ON_STARTUP: true/false; if true, attempts a ping on startup for quick validation
- ENABLE_SUPABASE: true/false; feature flag for Supabase integration
- SUPABASE_URL: Supabase project URL (required when ENABLE_SUPABASE=true)
- SUPABASE_ANON_KEY: Supabase anon key (required when ENABLE_SUPABASE=true)
- ENABLE_NLQ: true/false; enables the /nlq endpoints
- ENABLE_NLQ_AI: true/false; placeholder for future AI-augmented NLQ parsing
- OPENAI_API_KEY: Optional key for future AI integrations

Note: When MONGO_URI or database settings are not provided, /data and /nlq routes will respond with 503 errors. The app still runs and health endpoints will function for liveness checks.

## Running the App

### Local Development (uvicorn)
From the fastapi_backend directory:
```
export $(grep -v '^#' .env | xargs) 2>/dev/null || true
uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-3001} --reload
```
- The API will be available at http://localhost:3001 by default.
- Interactive docs: http://localhost:3001/docs
- OpenAPI JSON: http://localhost:3001/openapi.json

On Windows (PowerShell), you can rely on the app automatically loading .env. To override just the port:
```
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

### Preview/Container Run
If your environment provides a preview service (e.g., cloud dev environment), use either `uvicorn` or `python run.py`. Ensure:
- The service exposes the configured PORT (default 3001).
- A .env file is present in the fastapi_backend working directory.

## Generating OpenAPI Spec
A helper script is available to dump the OpenAPI schema into interfaces/openapi.json:
```
python -m src.api.generate_openapi
```
This imports the FastAPI app object and writes the current schema to interfaces/openapi.json.

## MongoDB Connection
The application uses Motor (AsyncIOMotorClient). On startup:
- If MONGO_URI is provided, the shared client is initialized.
- If MONGO_PING_ON_STARTUP is true, the app attempts a ping to validate connectivity.
- If MongoDB is unavailable, errors are logged but the app continues to run.

Basic example values:
```
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=exampledb
MONGO_COLLECTION=items
```

Connection examples in code (see src/db/mongo.py):
- Connect on startup:
  - The app calls connect_client(ping=bool(MONGO_PING_ON_STARTUP))
- Access default collection:
  - get_collection() uses MONGO_DB_NAME and MONGO_COLLECTION

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
These routes expect a configured MongoDB and collection.

- Create:
  ```
  curl -s -X POST http://localhost:3001/data \
    -H "Content-Type: application/json" \
    -d '{"data":{"name":"Alice","age":30,"country":"US"}}'
  ```

- Get by id:
  ```
  curl -s http://localhost:3001/data/<id>
  ```

- List (filter, projection, sorting, paging):
  ```
  # Filter: data.country == "US"; fields: data.name,data.age; sort by age desc; limit 10; offset 0
  curl -G -s http://localhost:3001/data \
    --data-urlencode 'filter={"data.country":"US"}' \
    --data-urlencode 'fields=data.name,data.age' \
    --data-urlencode 'sort_by=data.age' \
    --data-urlencode 'sort_dir=desc' \
    --data-urlencode 'limit=10' \
    --data-urlencode 'offset=0'
  ```

- Update:
  ```
  curl -s -X PUT http://localhost:3001/data/<id> \
    -H "Content-Type: application/json" \
    -d '{"data":{"name":"Alice","age":31}}'
  ```

- Delete:
  ```
  curl -s -X DELETE -i http://localhost:3001/data/<id>
  ```

### NLQ (/nlq/query)
NLQ parsing is rule-based and deterministic. It supports simple phrases like:
- today, yesterday, last 7 days/weeks/months
- field equals X, field is X
- field > N, field >= N, field < N, field <= N
- category: Retail, category in A,B,C
- field contains text
- sort by field [asc|desc]
- top N, limit N, offset N
- fields a,b,c or select a,b,c

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
        "collection": "orders",
        "params": {"limit": 20, "offset": 0, "sort_by": "created_at", "sort_dir": "desc", "fields":["_id","created_at","total"]}
      }'
```

Response (schema):
```
{
  "nlq": "<original query>",
  "filter": { ... parsed MongoDB-style filter ... },
  "items": [ { "_id": "...", ... }, ... ],
  "meta": { "total": 100, "limit": 20, "offset": 0 }
}
```

Note: If ENABLE_NLQ=false, the endpoint returns 404.

## Supabase Integration
- Controlled by ENABLE_SUPABASE.
- When enabled, the system attempts to initialize a Supabase client using SUPABASE_URL and SUPABASE_ANON_KEY.
- The /health endpoint logs a minimal Supabase health summary.
- No routes currently require Supabase to operate; it is optional.

## CORS
CORS is configured via the CORS_ALLOWED_ORIGINS environment variable. Provide a comma-separated list of origins or "*" to allow all. The app configures CORSMiddleware accordingly.

## Logging
Logs are emitted in a lightweight JSON-like structure to stdout with fields for timestamp, level, logger name, message, and context. Configure verbosity using LOG_LEVEL.

## Troubleshooting
- 503 Database not available: Ensure MONGO_URI, MONGO_DB_NAME, and MONGO_COLLECTION are correctly set and MongoDB is reachable.
- Invalid ObjectId: Confirm the id string is a 24-character hex value.
- NLQ returns few/no results: The NLQ parser is rule-based; refine the query or use explicit parameters with /data.
- CORS blocked in browser: Confirm CORS_ALLOWED_ORIGINS includes your frontend origin or "*" for permissive setups.

## Project Layout
- src/api/main.py: FastAPI app initialization and routing
- src/routers: Route modules (/health, /data, /nlq)
- src/db/mongo.py: Async MongoDB client management and helpers
- src/models/schemas.py: Pydantic schemas for requests and responses
- src/services/nlq_service.py: Deterministic NLQ parsing
- src/services/supabase_client.py: Optional Supabase wrapper
- src/api/generate_openapi.py: Utility to generate OpenAPI JSON
- interfaces/openapi.json: OpenAPI schema output (can be generated)
- run.py: Uvicorn launcher that reads PORT from settings
- requirements.txt: Python dependencies
