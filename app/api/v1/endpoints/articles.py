"""
articles.py (endpoints)
-----------------------
Endpoint REST API untuk operasi artikel:
- GET  /articles                    — list artikel dengan filter & pagination
- GET  /articles/{id}               — detail satu artikel
- POST /articles/{id}/summarize     — ringkas satu artikel secara manual
- POST /articles/{id}/generate      — generate artikel lengkap dengan AI
- POST /articles/summarize-all      — ringkas semua artikel yang belum diringkas
- DELETE /articles                  — hapus semua artikel pada tanggal tertentu
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_article_service
from app.models.article import ArticleListResponse, ArticleResponse, GenerateArticleResponse, SummarizeArticleResponse
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


@router.post(
    "/summarize-all",
    summary="Ringkas semua artikel yang belum diringkas",
    description=(
        "Memproses semua artikel di database yang belum memiliki ringkasan AI. "
        "Berguna untuk artikel lama atau artikel yang gagal diringkas saat scraping. "
        "Proses berjalan secara berurutan dengan jeda untuk menghindari rate limit Gemini."
    ),
    status_code=status.HTTP_200_OK,
)
async def summarize_all_articles(
    service: ArticleService = Depends(get_article_service),
) -> dict:
    """
    Endpoint untuk meringkas semua artikel yang belum punya ringkasan.

    Contoh: POST /api/v1/articles/summarize-all
    """
    result = await service.re_summarize_all()
    return {
        "status": "completed",
        "message": f"Berhasil meringkas {result['summarized']} dari {result['found']} artikel.",
        "articles_found": result["found"],
        "articles_summarized": result["summarized"],
    }


@router.delete(
    "/",
    summary="Hapus artikel berdasarkan tanggal",
    description=(
        "Menghapus semua artikel pada tanggal tertentu dari database. "
        "Berguna untuk membersihkan data sebelum melakukan scraping ulang. "
        "Parameter `source` opsional — jika tidak diisi, semua sumber dihapus."
    ),
    status_code=status.HTTP_200_OK,
)
async def delete_articles_by_date(
    target_date: date = Query(
        ...,
        alias="date",
        description="Tanggal artikel yang akan dihapus (format: YYYY-MM-DD)",
        example="2026-06-01",
    ),
    source: Optional[str] = Query(
        None,
        description="Filter portal sumber yang akan dihapus: kompas | detik | tempo. Kosongkan untuk hapus semua.",
        example="kompas",
    ),
    service: ArticleService = Depends(get_article_service),
) -> dict:
    """
    Endpoint untuk menghapus artikel berdasarkan tanggal (dan opsional sumber).

    Contoh:
    - DELETE /api/v1/articles/?date=2026-06-01              (hapus semua sumber)
    - DELETE /api/v1/articles/?date=2026-06-01&source=detik (hapus detik saja)
    """
    result = await service.delete_articles_by_date(target_date, source=source)
    source_label = source.capitalize() if source else "semua sumber"
    return {
        "status": "success",
        "message": f"Berhasil menghapus {result['deleted']} artikel tanggal {target_date} dari {source_label}.",
        "deleted": result["deleted"],
        "date": result["date"],
        "source": result["source"],
    }


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
    "/{article_id}/summarize",
    response_model=SummarizeArticleResponse,
    summary="Ringkas satu artikel secara manual",
    description=(
        "Meringkas konten satu artikel menggunakan Gemini AI dan menyimpan "
        "hasilnya (summary + tags) ke database. Berguna sebagai alternatif "
        "summarize otomatis saat scraping yang sering terkendala token expired."
    ),
    status_code=status.HTTP_200_OK,
)
async def summarize_article(
    article_id: str,
    service: ArticleService = Depends(get_article_service),
) -> SummarizeArticleResponse:
    """
    Endpoint untuk meringkas satu artikel secara manual via klik tombol.

    Contoh: POST /api/v1/articles/665f1a2b3c4d5e6f7a8b9c0d/summarize
    """
    result = await service.summarize_article(article_id)

    if result.status == "failed":
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
