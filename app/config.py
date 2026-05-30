"""
config.py
---------
Konfigurasi aplikasi menggunakan Pydantic Settings.
Semua nilai sensitif dibaca dari file .env secara otomatis.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    """
    Kelas utama konfigurasi aplikasi.
    Pydantic akan otomatis memuat variabel dari file .env.
    """

    # --- Informasi Aplikasi ---
    app_name: str = "News Aggregator & Summarizer API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    log_level: str = "INFO"

    # --- MongoDB ---
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "news_aggregator"

    # --- AI (Gemini) ---
    gemini_api_key: str = ""

    # --- CORS ---
    # Daftar origin yang diizinkan mengakses API (biasanya frontend URL)
    cors_origins: List[str] = ["http://localhost:3000"]

    # --- Scraper ---
    # Delay (detik) antar request untuk menghindari rate-limiting
    scraper_min_delay: float = 1.0
    scraper_max_delay: float = 3.0
    # Jumlah maksimal retry jika request gagal
    scraper_max_retries: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Mengembalikan instance Settings yang di-cache (Singleton pattern).
    Gunakan fungsi ini di seluruh aplikasi agar .env hanya dibaca sekali.
    """
    return Settings()


# Instance global yang bisa langsung diimpor
settings = get_settings()
