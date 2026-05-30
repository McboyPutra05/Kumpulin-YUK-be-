"""
scraper.py (endpoints)
----------------------
Endpoint REST API untuk memicu proses scraping:
- POST /scrape — trigger scraping untuk tanggal dan sumber tertentu
"""

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import get_article_service
from app.models.article import ScrapeRequest, ScrapeStatusResponse
from app.services.article_service import ArticleService

router = APIRouter(prefix="/scrape", tags=["Scraper"])


@router.post(
    "/",
    response_model=ScrapeStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger scraping artikel",
    description=(
        "Memulai proses scraping artikel berita dari portal yang dipilih "
        "untuk tanggal tertentu. Proses dijalankan secara sinkron (tunggu hingga selesai)."
    ),
)
async def trigger_scrape(
    request: ScrapeRequest,
    service: ArticleService = Depends(get_article_service),
) -> ScrapeStatusResponse:
    """
    Endpoint untuk memulai proses scraping.

    Menerima body JSON:
    ```json
    {
        "date": "2025-01-15",
        "sources": ["kompas", "detik"]
    }
    ```

    NOTE untuk pengembangan lebih lanjut:
    Saat ini scraping berjalan secara synchronous (request menunggu hingga selesai).
    Untuk produksi, gunakan Celery + Redis atau FastAPI BackgroundTasks untuk
    menjalankan scraping di background agar tidak ada request timeout.
    """
    result = await service.scrape_and_save(
        target_date=request.date,
        sources=request.sources,
    )
    return result
