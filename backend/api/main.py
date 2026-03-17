"""
FastAPI application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from backend.api.routers import experiments as experiments_router
from backend.api.routers import samples as samples_router
from backend.api.routers import chemicals as chemicals_router
from backend.api.routers import analysis as analysis_router
from backend.api.routers import conditions as conditions_router
from backend.api.routers import results as results_router
from backend.api.routers import dashboard as dashboard_router

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Experiment Tracking System API",
    description="Backend API for laboratory experiment tracking",
    version="1.0.0"
)

# CORS configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experiments_router.router)
app.include_router(samples_router.router)
app.include_router(chemicals_router.router)
app.include_router(analysis_router.router)
app.include_router(conditions_router.router)
app.include_router(results_router.router)
app.include_router(dashboard_router.router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "experiment_tracking_api"}

# API docs
@app.get("/api/docs", include_in_schema=False)
async def redirect_docs():
    """Redirect to Swagger UI"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Experiment Tracking System API",
        "docs": "http://localhost:8000/docs",
        "redoc": "http://localhost:8000/redoc"
    }

# TODO: Add routers for:
# - /api/results
# - /api/bulk_uploads
# - /api/dashboard

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
