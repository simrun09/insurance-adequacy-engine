"""
api.py — FastAPI application for the Insurance Adequacy Engine.

Single responsibility: accept HTTP requests, validate input, call the service
layer, and return serialized responses. No domain logic lives here.
"""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .schemas import AssessmentResult, UserProfile
from .service import assess

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Insurance Adequacy Engine",
    description="Budget-constrained insurance adequacy assessment for the Indian market.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    """Liveness check for load balancers and deployment verification."""
    return {"status": "healthy"}


@app.post("/assess", response_model=AssessmentResult)
def assess_endpoint(profile: UserProfile) -> AssessmentResult:
    """
    Run a full insurance adequacy assessment for the submitted user profile.

    FastAPI validates the request body against UserProfile automatically.
    Invalid input never reaches this function — it returns a 422 with
    field-level error messages before the function body executes.

    Any unexpected error from the engine is caught and returned as a clean
    500 JSON response. Stack traces are never exposed to API consumers.
    """
    try:
        return assess(profile)
    except Exception:
        logger.exception("Unhandled error in assess_endpoint")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal assessment error. Please try again."},
        )
