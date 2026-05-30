"""
main.py
-------
Entry point untuk aplikasi FastAPI.
Di sini kita mendaftarkan semua router, middleware, dan event handler.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.client import connect_to_mongo, close_mongo_connection
from app.api.v1.router import api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager untuk mengelola startup dan shutdown aplikasi.
    - Startup: Membuka koneksi ke MongoDB.
    - Shutdown: Menutup koneksi ke MongoDB dengan bersih.
    """
    # --- Startup ---
    print(f"[START] Starting {settings.app_name} v{settings.app_version}...")
    await connect_to_mongo()
    print("[OK] Database connection established.")
    
    yield  # Aplikasi berjalan di sini
    
    # --- Shutdown ---
    print("[STOP] Shutting down application...")
    await close_mongo_connection()
    print("[OK] Database connection closed.")


# Inisialisasi aplikasi FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API untuk News Aggregator & Summarizer dari portal berita Indonesia.",
    docs_url="/docs",       # Swagger UI tersedia di /docs
    redoc_url="/redoc",     # ReDoc tersedia di /redoc
    lifespan=lifespan,
)

# --- Middleware ---
# Konfigurasi CORS agar frontend (Next.js) bisa mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Router ---
# Semua endpoint API v1 dikelompokkan di bawah prefix /api/v1
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Endpoint untuk mengecek status aplikasi.
    Berguna untuk monitoring dan readiness probe.
    """
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }
