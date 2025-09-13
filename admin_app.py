from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

from src.metrics import summarize, tail

app = FastAPI(title="ParsingPhoneNumbers Admin")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/summary")
def api_summary():
    return JSONResponse(summarize())


@app.get("/logs")
def logs(n: int = 200):
    return PlainTextResponse("".join(tail(n)))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    data = summarize()
    tmpl = env.get_template("dashboard.html")
    return HTMLResponse(tmpl.render(data=data))
