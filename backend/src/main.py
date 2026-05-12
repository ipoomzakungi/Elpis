from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import (
    backtests,
    data_quality,
    data_sources,
    features,
    market_data,
    providers,
    regimes,
    research,
    research_execution,
    xau,
    xau_reaction,
)
from src.config import get_settings
from src.providers.errors import ProviderError

app = FastAPI(
    title="Elpis OI Regime Lab",
    description="Research dashboard for crypto market regime classification",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(market_data.router, prefix="/api/v1", tags=["market-data"])
app.include_router(providers.router, prefix="/api/v1", tags=["providers"])
app.include_router(features.router, prefix="/api/v1", tags=["features"])
app.include_router(regimes.router, prefix="/api/v1", tags=["regimes"])
app.include_router(data_quality.router, prefix="/api/v1", tags=["data-quality"])
app.include_router(backtests.router, prefix="/api/v1", tags=["backtests"])
app.include_router(data_sources.router, prefix="/api/v1", tags=["data-sources"])
app.include_router(research.router, prefix="/api/v1", tags=["research"])
app.include_router(research_execution.router, prefix="/api/v1", tags=["research-execution"])
app.include_router(xau.router, prefix="/api/v1", tags=["xau"])
app.include_router(xau_reaction.router, prefix="/api/v1", tags=["xau-reaction"])


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": details,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        if "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        if {"code", "message", "details"}.issubset(exc.detail):
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    if exc.status_code == 400:
        code = "VALIDATION_ERROR"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 429:
        code = "RATE_LIMITED"
    else:
        code = "INTERNAL_ERROR"

    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "details": []}},
    )


@app.exception_handler(ProviderError)
async def provider_exception_handler(request: Request, exc: ProviderError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Elpis OI Regime Lab",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
