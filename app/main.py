"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import init_db
from .routes import emails, pages, reviews, workflows
from .schemas import HealthResponse

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def _startup() -> None:  # pragma: no cover - FastAPI startup side effect
    init_db()


app.include_router(pages.router)
app.include_router(emails.router)
app.include_router(reviews.router)
app.include_router(workflows.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
