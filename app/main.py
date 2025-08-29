from fastapi import FastAPI

app = FastAPI(title="CSV->API Maker")


@app.get("/")
def root():
    return {"name": "CSV->API Maker", "version": "0.1"}


@app.get("/healthz")
def health():
    return {"status": "good"}
