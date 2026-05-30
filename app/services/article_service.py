"""
article_service.py
------------------
Business Logic Layer — mengorkestrasikan scraper, AI summarizer, dan repository.
Endpoint API tidak berinteraksi langsung dengan database atau scraper;
semua logika bisnis ada di sini.
"""

import asyncio
from datetime import date
from typing import Optional

from app.db.repositories.article_repo import ArticleRepository
from app.models.article import (
    ArticleCreate,
    ArticleListResponse,
    ArticleResponse,
    ArticleUpdate,
    GenerateArticleResponse,
    ScrapeStatusResponse,
)
from app.scraper.sources.kompas import KompasScraper
from app.scraper.sources.detik import DetikScraper
from app.scraper.sources.tempo import TempoScraper
from app.scraper.base_scraper import BaseScraper
from app.services.summarizer import summarizer_service
from app.services.article_generator import article_generator_service
from bson import ObjectId


# Registry scraper: menghubungkan nama sumber ke kelasnya
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "kompas": KompasScraper,
    "detik": DetikScraper,
    "tempo": TempoScraper,
}


class ArticleService:
    """
    Mengorkestrasi semua operasi yang berkaitan dengan artikel:
    - Scraping dari portal berita
    - Penyimpanan ke MongoDB (dengan dedup berdasarkan URL)
    - Summarisasi dengan Gemini AI
    - Pengambilan data untuk API response
    """

    def __init__(self, repo: ArticleRepository):
        self.repo = repo

    async def get_articles(
        self,
        published_date: Optional[date] = None,
        source: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> ArticleListResponse:
        """
        Mengambil daftar artikel dari database dengan filter dan pagination.
        """
        articles_raw, total = await self.repo.find_many(
            published_date=published_date,
            source=source,
            page=page,
            limit=limit,
        )

        # Konversi raw MongoDB dict ke Pydantic response model
        articles = [self._doc_to_response(doc) for doc in articles_raw]

        total_pages = (total + limit - 1) // limit  # Ceiling division

        return ArticleListResponse(
            articles=articles,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def get_article_by_id(self, article_id: str) -> Optional[ArticleResponse]:
        """
        Mengambil satu artikel berdasarkan ID-nya.
        """
        doc = await self.repo.find_by_id(article_id)
        if not doc:
            return None
        return self._doc_to_response(doc)

    async def generate_article(self, article_id: str) -> GenerateArticleResponse:
        """
        Menggenerate artikel berita lengkap dari data scraping menggunakan AI.

        Proses:
        1. Ambil artikel mentah (dengan content) dari database
        2. Kirim ke Gemini dengan prompt expert jurnalis
        3. Simpan hasil generate ke database
        4. Kembalikan hasilnya ke caller

        Args:
            article_id: MongoDB ObjectId artikel yang akan digenerate.

        Returns:
            GenerateArticleResponse: Berisi status dan teks artikel hasil generate.
        """
        # Ambil dokumen mentah (termasuk field 'content' yang tidak ada di ArticleResponse)
        doc = await self.repo.find_by_id(article_id)
        if not doc:
            return GenerateArticleResponse(
                article_id=article_id,
                status="failed",
                message=f"Artikel dengan ID '{article_id}' tidak ditemukan.",
            )

        if not doc.get("content"):
            return GenerateArticleResponse(
                article_id=article_id,
                status="failed",
                message="Artikel tidak memiliki konten untuk digenerate.",
            )

        try:
            print(f"\n🤖 Generating artikel untuk ID: {article_id[:8]}...")
            generated_text = await article_generator_service.generate(doc)

            # Simpan hasil ke database
            update_data = ArticleUpdate(
                generated_article=generated_text,
                is_generated=True,
            )
            await self.repo.update_one(article_id, update_data=update_data)
            print(f"   ✅ Artikel berhasil digenerate dan disimpan.")

            return GenerateArticleResponse(
                article_id=article_id,
                status="success",
                message="Artikel berhasil digenerate.",
                generated_article=generated_text,
            )

        except Exception as e:
            print(f"   ❌ Gagal generate artikel {article_id}: {e}")
            return GenerateArticleResponse(
                article_id=article_id,
                status="failed",
                message=f"Gagal generate artikel: {str(e)}",
            )

    async def scrape_and_save(
        self, target_date: date, sources: list[str]
    ) -> ScrapeStatusResponse:
        """
        Mengorkestrasi proses scraping lengkap:
        1. Jalankan scraper untuk setiap portal yang diminta
        2. Simpan artikel baru ke MongoDB (skip duplikat berdasarkan URL)
        3. Ringkas semua artikel yang baru disimpan menggunakan AI

        Args:
            target_date: Tanggal berita yang akan di-scrape.
            sources: Daftar nama portal ("kompas", "detik", "tempo").

        Returns:
            ScrapeStatusResponse: Ringkasan hasil proses.
        """
        # Validasi sumber yang diminta
        valid_sources = [s.lower() for s in sources if s.lower() in SCRAPER_REGISTRY]
        if not valid_sources:
            return ScrapeStatusResponse(
                task_id="N/A",
                status="failed",
                message=f"Sumber tidak valid. Pilih dari: {list(SCRAPER_REGISTRY.keys())}",
            )

        total_scraped = 0
        total_summarized = 0
        new_article_ids: list[str] = []

        # Jalankan setiap scraper secara berurutan untuk menghindari beban berat
        for source_name in valid_sources:
            scraper_class = SCRAPER_REGISTRY[source_name]

            async with scraper_class() as scraper:
                raw_articles = await scraper.scrape_by_date(target_date)

            # Simpan artikel yang belum ada (deduplikasi berdasarkan URL)
            for raw in raw_articles:
                if await self.repo.url_exists(raw.url):
                    print(f"   ⏭️ Skip (sudah ada): {raw.url[:60]}...")
                    continue

                article_data = ArticleCreate(
                    title=raw.title,
                    url=raw.url,
                    source=raw.source,
                    published_date=raw.published_date,
                    content=raw.content,
                )
                article_id = await self.repo.insert_one(article_data)
                new_article_ids.append(article_id)
                total_scraped += 1

        # Summarisasi semua artikel yang baru disimpan
        if new_article_ids:
            print(f"\n🤖 Memulai summarisasi {len(new_article_ids)} artikel...")
            total_summarized = await self._summarize_articles(new_article_ids)

        return ScrapeStatusResponse(
            task_id=f"scrape_{target_date}",
            status="completed",
            message=f"Scraping selesai. {total_scraped} artikel baru dari {', '.join(valid_sources)}.",
            articles_scraped=total_scraped,
            articles_summarized=total_summarized,
        )

    async def _summarize_articles(self, article_ids: list[str]) -> int:
        """
        Mengambil artikel berdasarkan ID dan meringkas kontennya menggunakan AI.
        
        Returns:
            int: Jumlah artikel yang berhasil diringkas.
        """
        summarized_count = 0

        for article_id in article_ids:
            doc = await self.repo.find_by_id(article_id)
            if not doc or not doc.get("content"):
                continue

            try:
                summary = await summarizer_service.summarize(doc["content"])
                # Gunakan ArticleUpdate model yang proper (bukan lambda — bug!)
                update_data = ArticleUpdate(summary=summary, is_summarized=True)
                await self.repo.update_one(article_id, update_data=update_data)
                summarized_count += 1
            except Exception as e:
                print(f"   ❌ Gagal summarisasi artikel {article_id}: {e}")

        return summarized_count

    @staticmethod
    def _doc_to_response(doc: dict) -> ArticleResponse:
        """
        Mengkonversi dokumen mentah MongoDB ke Pydantic ArticleResponse.
        Menangani konversi ObjectId ke string.
        """
        return ArticleResponse(
            id=str(doc["_id"]),
            title=doc["title"],
            url=doc["url"],
            source=doc["source"],
            published_date=doc["published_date"],
            summary=doc.get("summary"),
            is_summarized=doc.get("is_summarized", False),
            generated_article=doc.get("generated_article"),
            is_generated=doc.get("is_generated", False),
            scraped_at=doc["scraped_at"],
        )
