"""
client.py
---------
Mengelola koneksi ke MongoDB menggunakan Motor (async driver).
Menggunakan pola singleton agar hanya ada satu koneksi aktif
selama aplikasi berjalan (connection pooling).
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

# Variabel global untuk menyimpan instance client dan database.
# Akan diisi saat aplikasi startup.
_mongo_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """
    Membuka koneksi ke MongoDB.
    Dipanggil satu kali saat aplikasi FastAPI startup (lifespan).
    Jika MongoDB belum jalan, server tetap bisa start (hanya warning).
    """
    global _mongo_client, _database
    _mongo_client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=5000,  # Timeout lebih cepat agar tidak nunggu lama
    )
    _database = _mongo_client[settings.mongodb_db_name]

    # Ping untuk mengecek koneksi -- tapi tidak crash kalau gagal
    try:
        await _database.command("ping")
        print(f"[OK] Connected to MongoDB: '{settings.mongodb_db_name}'")
    except Exception as e:
        print(f"[WARNING] Tidak bisa konek ke MongoDB di '{settings.mongodb_url}'")
        print(f"   Error: {e}")
        print(f"   Server tetap berjalan, tapi fitur database tidak akan bekerja.")
        print(f"   Pastikan MongoDB sudah dijalankan, lalu restart server ini.")


async def close_mongo_connection() -> None:
    """
    Menutup koneksi MongoDB dengan bersih.
    Dipanggil saat aplikasi shutdown.
    """
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        print("[OK] MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """
    Mengembalikan instance database aktif.
    Digunakan sebagai FastAPI dependency injection di endpoint.

    Raises:
        RuntimeError: Jika koneksi belum dibuka (seharusnya tidak terjadi jika lifespan benar).
    """
    if _database is None:
        raise RuntimeError(
            "Database connection has not been established. "
            "Ensure 'connect_to_mongo()' was called during app startup."
        )
    return _database
