import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import AI_MODE
from .db import Base, engine
from .routes import auth_routes, diagnostic, reports, dashboard

Base.metadata.create_all(bind=engine)

if AI_MODE == "mock":
    logging.getLogger("app").warning(
        "AI_MODE is 'mock': open answers are scored with canned responses. "
        "Do not use this mode for real assessments."
    )

app = FastAPI(title="AI Pulse API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(diagnostic.router)
app.include_router(reports.router)
app.include_router(dashboard.router)


@app.get("/health")
def health():
    return {"status": "ok", "ai_mode": AI_MODE}
