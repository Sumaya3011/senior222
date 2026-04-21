from fastapi import APIRouter
from fastapi.responses import FileResponse

import services.ee_runtime as ee_runtime

router = APIRouter()


@router.get("/")
def serve_frontend():
    return FileResponse("index.html")


@router.get("/terrascope-logo.png")
def serve_logo():
    return FileResponse("terrascope-logo.png", media_type="image/png")


@router.get("/welcome-brand-logo.png")
def serve_welcome_brand_logo():
    return FileResponse("welcome-brand-logo.png", media_type="image/png")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "ee_ready": ee_runtime.EE_READY,
        "ee_error": ee_runtime.EE_ERROR,
    }
