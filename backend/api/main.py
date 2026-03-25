"""FastAPI application entry point."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from backend.config.settings import get_settings
from backend.api.routers import (
    experiments, conditions, results, samples,
    chemicals, analysis, dashboard, admin, bulk_uploads,
)

settings = get_settings()

app = FastAPI(
    title="Experiment Tracking System API",
    description="Backend API for laboratory experiment tracking",
    version="1.0.0",
    openapi_tags=[
        {"name": "experiments", "description": "Experiment CRUD and notes"},
        {"name": "conditions", "description": "Experimental conditions and calculation engine"},
        {"name": "results", "description": "Scalar, ICP, and file results"},
        {"name": "samples", "description": "Sample inventory"},
        {"name": "chemicals", "description": "Compound library and chemical additives"},
        {"name": "analysis", "description": "XRD, pXRF, and external analyses"},
        {"name": "dashboard", "description": "Reactor status and experiment timelines"},
        {"name": "admin", "description": "Recalculation and maintenance endpoints"},
        {"name": "bulk-uploads", "description": "Bulk data upload via Excel/CSV"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API routers
app.include_router(experiments.router)
app.include_router(conditions.router)
app.include_router(results.router)
app.include_router(samples.router)
app.include_router(chemicals.router)
app.include_router(analysis.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(bulk_uploads.router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "experiment_tracking_api"}


# Serve React app from frontend/dist/ if built
_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve React SPA — static files from dist/, everything else returns index.html."""
        # Serve static files (images, etc.) from dist/ if they exist
        static_file = _DIST / full_path
        if full_path and static_file.is_file():
            return FileResponse(static_file)
        index = _DIST / "index.html"
        return FileResponse(index)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
