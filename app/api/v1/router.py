"""
router.py (API v1)
------------------
Aggregator router untuk API versi 1.
Mendaftarkan semua endpoint router di bawah prefix /api/v1.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import articles, scraper, auth

# Router utama yang akan diinclude di main.py
api_v1_router = APIRouter()

# Daftarkan semua endpoint router
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(articles.router)
api_v1_router.include_router(scraper.router)
