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


def sanitize_name(name: str) -> str:
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
