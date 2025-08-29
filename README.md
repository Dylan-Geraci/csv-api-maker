# csv-api-maker

Turn any CSV into a browsable REST API in minutes. Upload a file, get typed endpoints with filtering, sorting, and pagination.

## Why
Quickly explore datasets or wire CSVs into apps without writing custom backends.

## MVP (scope)
- Upload CSV → infer schema (int/float/bool/string/date)
- Load into SQLite
- Auto REST:
  - `POST /datasets` (upload)
  - `GET /datasets` (list)
  - `GET /datasets/{name}` (schema + sample)
  - `GET /datasets/{name}/rows?limit=&offset=&filter=&sort=`
- Auto OpenAPI docs (Swagger/Redoc)

## Tech
FastAPI + Uvicorn • SQLite • SQLAlchemy • pandas (type sniffing) • Docker (later)
