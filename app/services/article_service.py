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
    SummarizeArticleResponse,
    ScrapeStatusResponse,
)
from app.scraper.sources.kompas import KompasScraper
from app.scraper.sources.detik import DetikScraper
from app.scraper.sources.cnnindonesia import CNNIndonesiaScraper
from app.scraper.sources.liputan6 import Liputan6Scraper
from app.scraper.sources.kumparan import KumparanScraper
from app.scraper.base_scraper import BaseScraper
from app.services.summarizer import summarizer_service
from app.services.article_generator import article_generator_service
from bson import ObjectId


# Registry scraper: menghubungkan nama sumber ke kelasnya
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "kompas": KompasScraper,
    "detik": DetikScraper,
    "cnnindonesia": CNNIndonesiaScraper,
    "liputan6": Liputan6Scraper,
    "kumparan": KumparanScraper,
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

    async def summarize_article(self, article_id: str) -> SummarizeArticleResponse:
        """
        Meringkas satu artikel secara manual via klik tombol di frontend.

        Bisa dipakai ulang bahkan jika artikel sudah diringkas sebelumnya
        (akan overwrite summary yang lama dengan yang baru).

        Args:
            article_id: MongoDB ObjectId artikel yang akan diringkas.

        Returns:
            SummarizeArticleResponse: Berisi status, summary, dan tags hasil AI.
        """
        doc = await self.repo.find_by_id(article_id)
        if not doc:
            return SummarizeArticleResponse(
                article_id=article_id,
                status="failed",
                message=f"Artikel dengan ID '{article_id}' tidak ditemukan.",
            )

        if not doc.get("content"):
            return SummarizeArticleResponse(
                article_id=article_id,
                status="failed",
                message="Artikel tidak memiliki konten untuk diringkas.",
            )

        try:
            print(f"\n🤖 Summarizing artikel ID: {article_id[:8]}...")
            summary, tags = await summarizer_service.summarize(doc["content"])

            update_data = ArticleUpdate(summary=summary, tags=tags, is_summarized=True)
            await self.repo.update_one(article_id, update_data=update_data)
            print(f"   ✅ Artikel berhasil diringkas.")

            return SummarizeArticleResponse(
                article_id=article_id,
                status="success",
                message="Artikel berhasil diringkas.",
                summary=summary,
                tags=tags,
            )

        except Exception as e:
            print(f"   ❌ Gagal summarisasi artikel {article_id}: {e}")
            return SummarizeArticleResponse(
                article_id=article_id,
                status="failed",
                message=f"Gagal meringkas artikel: {str(e)}",
            )

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
        mengorkestrasi proses scraping lengkap:
        1. Jalankan scraper untuk setiap portal yang diminta
        2. Simpan artikel baru ke MongoDB (skip duplikat berdasarkan URL)
        3. Ringkas semua artikel yang baru disimpan menggunakan AI

        Args:
            target_date: Tanggal berita yang akan di-scrape.
            sources: Daftar nama portal ("kompas", "detik", "cnnindonesia", "liputan6", "kumparan").

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

        return ScrapeStatusResponse(
            task_id=f"scrape_{target_date}",
            status="completed",
            message=(
                f"Scraping selesai. {total_scraped} artikel baru dari {', '.join(valid_sources)}. "
                f"Klik tombol 'Ringkas' pada tiap artikel untuk mendapatkan ringkasan AI."
            ),
            articles_scraped=total_scraped,
            articles_summarized=0,
        )

    async def delete_articles_by_date(
        self, target_date: date, source: Optional[str] = None
    ) -> dict:
        """
        Menghapus semua artikel pada tanggal tertentu dari database.
        Berguna untuk membersihkan data sebelum scraping ulang.

        Args:
            target_date: Tanggal artikel yang akan dihapus.
            source: Opsional — filter berdasarkan portal (kompas/detik/tempo).

        Returns:
            dict: Berisi jumlah artikel yang berhasil dihapus.
        """
        deleted_count = await self.repo.delete_by_date(target_date, source=source)
        source_label = source.capitalize() if source else "semua sumber"
        print(f"🗑️ Dihapus {deleted_count} artikel tanggal {target_date} dari {source_label}.")
        return {"deleted": deleted_count, "date": str(target_date), "source": source or "all"}

    async def _summarize_articles(self, article_ids: list[str]) -> int:
        """
        Mengambil artikel berdasarkan ID dan meringkas kontennya menggunakan AI.
        Juga mengekstrak 4 tag SEO dari setiap artikel.
        
        Returns:
            int: Jumlah artikel yang berhasil diringkas.
        """
        summarized_count = 0

        for article_id in article_ids:
            doc = await self.repo.find_by_id(article_id)
            if not doc or not doc.get("content"):
                continue

            try:
                summary, tags = await summarizer_service.summarize(doc["content"])
                # Gunakan ArticleUpdate model yang proper (bukan lambda — bug!)
                update_data = ArticleUpdate(summary=summary, tags=tags, is_summarized=True)
                await self.repo.update_one(article_id, update_data=update_data)
                summarized_count += 1
            except Exception as e:
                print(f"   ❌ Gagal summarisasi artikel {article_id}: {e}")

        return summarized_count

    async def re_summarize_all(self) -> dict:
        """
        Memproses semua artikel yang belum memiliki ringkasan AI.
        Berguna untuk artikel lama yang di-scrape sebelum fitur summarisasi aktif,
        atau artikel yang gagal diringkas saat pertama kali.

        Returns:
            dict: Berisi total artikel yang ditemukan dan jumlah yang berhasil diringkas.
        """
        docs = await self.repo.find_unsummarized(limit=200)
        total_found = len(docs)

        if total_found == 0:
            print("✅ Semua artikel sudah memiliki ringkasan.")
            return {"found": 0, "summarized": 0}

        print(f"\n🤖 Memulai re-summarize {total_found} artikel yang belum diringkas...")
        article_ids = [str(doc["_id"]) for doc in docs]
        summarized_count = await self._summarize_articles(article_ids)
        print(f"✅ Re-summarize selesai: {summarized_count}/{total_found} artikel berhasil.")

        return {"found": total_found, "summarized": summarized_count}

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
            tags=doc.get("tags", []),
            is_summarized=doc.get("is_summarized", False),
            generated_article=doc.get("generated_article"),
            is_generated=doc.get("is_generated", False),
            scraped_at=doc["scraped_at"],
        )
