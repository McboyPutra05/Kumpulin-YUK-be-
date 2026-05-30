"""
article.py (models)
-------------------
Mendefinisikan struktur data (schema) artikel menggunakan Pydantic.
Model ini digunakan untuk validasi data masuk/keluar di API,
dan sebagai representasi dokumen di MongoDB.
"""

from datetime import datetime, date as _Date
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(str):
    """
    Custom type untuk menangani ObjectId milik MongoDB agar kompatibel dengan Pydantic v2.
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value, _info=None):
        if not ObjectId.is_valid(value):
            raise ValueError(f"Invalid ObjectId: {value}")
        return str(value)


class ArticleBase(BaseModel):
    """
    Field dasar yang dimiliki semua model artikel.
    Digunakan sebagai base class untuk inheritance.
    """
    title: str = Field(..., description="Judul lengkap artikel berita", min_length=5)
    url: str = Field(..., description="URL asli artikel di portal berita")
    source: str = Field(..., description="Nama portal sumber (kompas/detik/tempo)")
    published_date: _Date = Field(..., description="Tanggal artikel dipublikasikan (YYYY-MM-DD)")


class ArticleCreate(ArticleBase):
    """
    Schema untuk membuat dokumen artikel baru di database.
    Berisi field tambahan yang diisi saat proses scraping.
    """
    content: str = Field(..., description="Isi artikel lengkap yang di-scrape", min_length=50)
    summary: Optional[str] = Field(None, description="Ringkasan 1 paragraf yang dihasilkan oleh AI")
    is_summarized: bool = Field(default=False, description="Status apakah artikel sudah diringkas oleh AI")
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="Waktu artikel di-scrape")


class ArticleUpdate(BaseModel):
    """
    Schema untuk mengupdate dokumen artikel (partial update / PATCH).
    Semua field bersifat opsional.
    """
    summary: Optional[str] = Field(None, description="Ringkasan hasil AI yang diperbarui")
    is_summarized: Optional[bool] = None
    generated_article: Optional[str] = Field(None, description="Artikel berita lengkap yang digenerate AI")
    is_generated: Optional[bool] = None


class ArticleResponse(ArticleBase):
    """
    Schema respons API untuk satu artikel.
    Ini yang dikirim ke frontend — tidak menyertakan `content` mentah
    untuk menjaga payload tetap ringan.
    """
    id: str = Field(..., description="ID unik artikel (MongoDB ObjectId)")
    summary: Optional[str] = Field(None, description="Ringkasan artikel oleh AI")
    is_summarized: bool = Field(default=False)
    generated_article: Optional[str] = Field(None, description="Artikel berita lengkap hasil generate AI")
    is_generated: bool = Field(default=False)
    scraped_at: datetime

    model_config = {"from_attributes": True}


class ArticleListResponse(BaseModel):
    """
    Schema respons untuk endpoint list artikel.
    Menyertakan metadata pagination agar frontend bisa menampilkan pager.
    """
    articles: list[ArticleResponse]
    total: int = Field(..., description="Total artikel yang cocok dengan filter")
    page: int = Field(..., description="Halaman saat ini")
    limit: int = Field(..., description="Jumlah artikel per halaman")
    total_pages: int = Field(..., description="Total halaman yang tersedia")


class ScrapeRequest(BaseModel):
    """
    Schema request untuk endpoint trigger scraping.
    User mengirimkan tanggal dan daftar sumber yang ingin di-scrape.
    """
    date: _Date = Field(..., description="Tanggal berita yang ingin di-scrape (YYYY-MM-DD)")
    sources: list[str] = Field(
        default=["kompas", "detik", "tempo"],
        description="Daftar portal yang akan di-scrape",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2025-01-15",
                "sources": ["kompas", "detik"],
            }
        }
    }


class GenerateArticleResponse(BaseModel):
    """
    Schema respons untuk endpoint generate artikel.
    """
    article_id: str
    status: str = Field(..., description="Status: success | failed")
    message: str
    generated_article: Optional[str] = Field(None, description="Teks artikel berita yang digenerate")


class ScrapeStatusResponse(BaseModel):
    """
    Schema respons untuk pengecekan status background scraping job.
    """
    task_id: str
    status: str = Field(..., description="Status: pending | running | completed | failed")
    message: str
    articles_scraped: int = Field(default=0)
    articles_summarized: int = Field(default=0)
