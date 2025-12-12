"""FastAPI application entry point."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Log environment variables for debugging (without sensitive values)
logger.info("=== Environment Check ===")
logger.info(f"FMP_API_KEY set: {'FMP_API_KEY' in os.environ}")
logger.info(f"DATABASE_URL set: {'DATABASE_URL' in os.environ}")
logger.info("=========================")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Strategy Engine")
    yield
    logger.info("Shutting down Strategy Engine")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Strategy Engine",
        description="Strategy Engine API for S&P500 earnings-based trading signals",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check that doesn't depend on settings
    @app.get("/health")
    async def health_check():
        return {"ok": True}

    # Import and include other routes only if settings are available
    try:
        from app.core.config import get_settings
        settings = get_settings()
        logger.info(f"Settings loaded successfully")

        from app.api.routes import router
        app.include_router(router)
        logger.info("Routes registered successfully")
    except Exception as e:
        logger.error(f"Failed to load settings or routes: {e}")

        @app.get("/debug")
        async def debug_info():
            return {
                "error": str(e),
                "FMP_API_KEY_set": "FMP_API_KEY" in os.environ,
                "DATABASE_URL_set": "DATABASE_URL" in os.environ,
            }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
