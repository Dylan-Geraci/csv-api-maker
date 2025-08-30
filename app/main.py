from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
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
