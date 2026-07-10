"""FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload   (from the backend/ directory)
Docs: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db
from .routers import agents, auth, interview, nodes, workspace


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="NodeDash API",
    version="0.1.0",
    description=(
        "Backend for NodeDash: run the onboarding questionnaire, compile answers "
        "into a company operating graph, and expose each node as a login-gated window "
        "with its own AI Chief of Staff agent."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interview.router)
app.include_router(auth.router)
app.include_router(workspace.router)
app.include_router(nodes.router)
app.include_router(agents.router)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Registered handlers run inside the CORS middleware, so this 500 keeps its
    # CORS headers — otherwise the browser reports an opaque network/CORS failure
    # instead of a readable error.
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model if settings.llm_enabled else None,
    }
