from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api.routes import market_data, features, regimes, data_quality


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
app.include_router(features.router, prefix="/api/v1", tags=["features"])
app.include_router(regimes.router, prefix="/api/v1", tags=["regimes"])
app.include_router(data_quality.router, prefix="/api/v1", tags=["data-quality"])


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
