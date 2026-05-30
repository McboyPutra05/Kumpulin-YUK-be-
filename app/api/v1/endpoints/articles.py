"""
articles.py (endpoints)
-----------------------
Endpoint REST API untuk operasi artikel:
- GET /articles — list artikel dengan filter & pagination
- GET /articles/{id} — detail satu artikel
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_article_service
from app.models.article import ArticleListResponse, ArticleResponse, GenerateArticleResponse
from app.services.article_service import ArticleService

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get(
    "/",
    response_model=ArticleListResponse,
    summary="Ambil daftar artikel",
    description="Mengambil daftar artikel dengan filter tanggal, sumber, dan pagination.",
)
async def list_articles(
    published_date: Optional[date] = Query(
        None,
        alias="date",
        description="Filter berdasarkan tanggal publikasi (format: YYYY-MM-DD)",
        example="2025-01-15",
    ),
    source: Optional[str] = Query(
        None,
        description="Filter berdasarkan portal sumber: kompas | detik | tempo",
        example="kompas",
    ),
    page: int = Query(1, ge=1, description="Nomor halaman (mulai dari 1)"),
    limit: int = Query(20, ge=1, le=100, description="Jumlah artikel per halaman (maks 100)"),
    service: ArticleService = Depends(get_article_service),
) -> ArticleListResponse:
    """
    Endpoint untuk mengambil daftar artikel.
    
    Contoh request:
    - GET /api/v1/articles?date=2025-01-15
    - GET /api/v1/articles?date=2025-01-15&source=kompas&page=2
    """
    return await service.get_articles(
        published_date=published_date,
        source=source,
        page=page,
        limit=limit,
    )


@router.get(
    "/{article_id}",
    response_model=ArticleResponse,
    summary="Ambil detail satu artikel",
    description="Mengambil data lengkap satu artikel berdasarkan ID-nya.",
)
async def get_article(
    article_id: str,
    service: ArticleService = Depends(get_article_service),
) -> ArticleResponse:
    """
    Endpoint untuk mengambil detail satu artikel.
    
    Contoh: GET /api/v1/articles/665f1a2b3c4d5e6f7a8b9c0d
    """
    article = await service.get_article_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artikel dengan ID '{article_id}' tidak ditemukan.",
        )
    return article


@router.post(
    "/{article_id}/generate",
    response_model=GenerateArticleResponse,
    summary="Generate artikel berita dari data scraping",
    description=(
        "Menggenerate artikel berita lengkap bergaya jurnalistik profesional "
        "dari konten artikel yang telah di-scrape, menggunakan Gemini AI. "
        "Hasilnya disimpan ke database dan dikembalikan dalam respons."
    ),
    status_code=status.HTTP_200_OK,
)
async def generate_article(
    article_id: str,
    service: ArticleService = Depends(get_article_service),
) -> GenerateArticleResponse:
    """
    Endpoint untuk menggenerate artikel berita lengkap dari data scraping.

    Contoh: POST /api/v1/articles/665f1a2b3c4d5e6f7a8b9c0d/generate
    """
    result = await service.generate_article(article_id)

    if result.status == "failed":
        # Tentukan HTTP status code yang sesuai
        if "tidak ditemukan" in result.message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.message,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message,
        )

    return result
