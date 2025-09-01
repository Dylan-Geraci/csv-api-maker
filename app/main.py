from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app.models import Dataset
import pandas as pd
import json
import re

app = FastAPI(title="CSV->API Maker")


@app.on_event("startup")
def _init_db():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"name": "CSV->API Maker", "version": "0.1"}


@app.get("/healthz")
def health():
    return {"status": "good"}


def _sanitize_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    return safe.lower()[:120] or "dataset"


def _dtype_to_simple(dtype) -> str:
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    return "string"


@app.post("/datasets")
async def create_dataset(
    file: UploadFile = File(...),
    name: str = Form(None),
    db: Session = Depends(get_db),
):
    base_name = name or (file.filename.rsplit(
        ".", 1)[0] if file.filename else "dataset")
    table_name = f"ds_{_sanitize_name(base_name)}"

    if db.query(Dataset).filter_by(name=base_name).first():
        raise HTTPException(
            status_code=409, detail="Dataset name already exists.")

    try:
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    schema = [{"name": col, "type": _dtype_to_simple(
        dt)} for col, dt in df.dtypes.items()]

    try:
        df.to_sql(table_name, con=engine, if_exists="fail", index=False)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"DB error: {e}")

    meta = Dataset(
        name=base_name,
        table_name=table_name,
        schema_json=json.dumps(schema),
        row_count=int(len(df)),
    )
    db.add(meta)
    db.commit()

    return {"name": base_name, "rows": int(len(df)), "schema": schema, "table": table_name}


@app.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    return [
        {"name": ds.name, "rows": ds.row_count, "created_at": ds.created_at}
        for ds in db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    ]


def _get_dataset_or_404(db: Session, name: str) -> Dataset:
    ds = db.query(Dataset).filter_by(name=name).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@app.get("/datasets/{name}")
def get_dataset(name: str, db: Session = Depends(get_db)):
    ds = _get_dataset_or_404(db, name)
    schema = json.loads(ds.schema_json)
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(
            text(f"SELECT * FROM {ds.table_name} LIMIT :n"), {"n": 5}
        ).fetchall()]
    return {"name": ds.name, "rows": ds.row_count, "schema": schema, "sample": rows}


@app.delete("/datasets/{name}")
def delete_dataset(name: str, db: Session = Depends(get_db)):
    ds = _get_dataset_or_404(db, name)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {ds.table_name}"))
    db.delete(ds)
    db.commit()
    return {"message": f"Deleted dataset '{name}'."}


@app.get("/datasets/{name}/rows")
def get_rows(
        name: str,
        limit: int = 50,
        offset: int = 0,
        sort: str | None = None,
        filter: list[str] | None = Query(None),
        db: Session = Depends(get_db),):

    ds = _get_dataset_or_404(db, name)
    schema = json.loads(ds.schema_json)
    cols = {col["name"]: col["type"] for col in schema}

    # clamp limit
    limit = max(1, min(limit, 1000))
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    # helpers
    def parse_value(col: str, raw: str):
        t = cols[col]
        if t == "integer":
            return int(raw)
        if t == "float":
            return float(raw)
        if t == "boolean":
            return 1 if str(raw).lower() in ("1", "true", "t", "yes", "y") else 0
        if t == "datetime":
            return str(pd.to_datetime(raw))
        return raw

    # filters
    where_clauses = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if filter:
        for i, f in enumerate(filter):
            parts = f.split(":", 2)
            if len(parts) != 3:
                raise HTTPException(
                    status_code=400, detail="Bad filter format. Use col:op:value")
            col, op, raw = parts
            if col not in cols:
                raise HTTPException(
                    status_code=400, detail=f"Unknown column '{col}'")
            key = f"v{i}"

            if op == "eq":
                where_clauses.append(f'"{col}" = :{key}')
                params[key] = parse_value(col, raw)
            elif op in ("neq", "ne"):
                where_clauses.append(f'"{col}" <> :{key}')
                params[key] = parse_value(col, raw)
            elif op == "gt":
                where_clauses.append(f'"{col}" > :{key}')
                params[key] = parse_value(col, raw)
            elif op == "gte":
                where_clauses.append(f'"{col}" >= :{key}')
                params[key] = parse_value(col, raw)
            elif op == "lt":
                where_clauses.append(f'"{col}" < :{key}')
                params[key] = parse_value(col, raw)
            elif op == "lte":
                where_clauses.append(f'"{col}" <= :{key}')
                params[key] = parse_value(col, raw)
            elif op == "contains":
                where_clauses.append(f'"{col}" LIKE :{key}')
                params[key] = f"%{raw}%"
            else:
                raise HTTPException(
                    status_code=400, detail=f"Unsupported operator '{op}'")

    where_sql = (" WHERE " + " AND ".join(where_clauses)
                 ) if where_clauses else ""

    # sorting
    order_sql = ""
    if sort:
        try:
            scol, sdir = sort.split(":", 1)
        except ValueError:
            scol, sdir = sort, "asc"
        if scol not in cols:
            raise HTTPException(
                status_code=400, detail=f"Unknown sort column '{scol}'")
        sdir = sdir.lower()
        sdir = "desc" if sdir == "desc" else "asc"
        order_sql = f' ORDER BY "{scol}" {sdir.upper()}'

    # query
    with engine.connect() as conn:
        sql = text(
            f'SELECT * FROM {ds.table_name}{where_sql}{order_sql} LIMIT :limit OFFSET :offset')
        rows = [dict(r._mapping) for r in conn.execute(sql, params).fetchall()]

        total_params = {k: v for k,
                        v in params.items() if k not in ("limit", "offset")}
        total_sql = text(
            f'SELECT COUNT(*) AS c FROM {ds.table_name}{where_sql}')
        total = conn.execute(total_sql, total_params).scalar_one()

    return {"data": rows, "meta": {"limit": limit, "offset": offset, "total": int(total)}}
