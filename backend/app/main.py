from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, health
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Upload and track lease documents. RAG processing is intentionally deferred.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
app.include_router(documents.router)
