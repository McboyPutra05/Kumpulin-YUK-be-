"""
base_scraper.py
---------------
Abstract base class untuk semua scraper portal berita.
Menggunakan Template Method Pattern: mendefinisikan "alur" scraping yang konsisten,
sementara detail implementasi per-portal diserahkan ke subclass.
"""

import asyncio
import random
from abc import ABC, abstractmethod
from datetime import date
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.scraper.utils import get_random_user_agent


@dataclass
class RawArticle:
    """
    Representasi artikel mentah hasil scraping sebelum diproses lebih lanjut.
    Menggunakan dataclass untuk struktur data yang ringan dan immutable-friendly.
    """
    title: str
    url: str
    source: str
    published_date: date
    content: str = ""
    summary: Optional[str] = None
    is_summarized: bool = False


class BaseScraper(ABC):
    """
    Abstract base class yang mendefinisikan kontrak dan utilitas bersama
    untuk semua scraper portal berita.

    Cara menggunakannya: buat subclass dan implement semua method @abstractmethod.

    Contoh:
        class KompasScraper(BaseScraper):
            source_name = "kompas"
            ...
    """

    source_name: str = "base"  # Override di setiap subclass

    def __init__(self):
        # httpx.AsyncClient dengan timeout yang wajar untuk efisiensi
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Mendukung penggunaan sebagai async context manager."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),  # 30 detik timeout
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Memastikan koneksi HTTP ditutup dengan bersih."""
        if self._client:
            await self._client.aclose()

    async def _fetch(self, url: str) -> Optional[str]:
        """
        Mengambil konten HTML dari URL dengan penanganan:
        - Header User-Agent yang dirotasi
        - Retry dengan exponential backoff
        - Delay antar request untuk menghindari rate-limiting

        Returns:
            str: Konten HTML, atau None jika gagal setelah semua retry.
        """
        if not self._client:
            raise RuntimeError("Scraper harus digunakan sebagai context manager (async with).")

        for attempt in range(1, settings.scraper_max_retries + 1):
            try:
                headers = {"User-Agent": get_random_user_agent()}
                response = await self._client.get(url, headers=headers)
                response.raise_for_status()

                # Delay acak antar request (meniru perilaku manusia)
                await asyncio.sleep(
                    random.uniform(settings.scraper_min_delay, settings.scraper_max_delay)
                )
                return response.text

            except httpx.HTTPStatusError as e:
                print(f"⚠️ HTTP Error {e.response.status_code} saat mengambil {url} (attempt {attempt})")
                if e.response.status_code == 404:
                    return None  # 404 tidak perlu di-retry
            except httpx.RequestError as e:
                print(f"⚠️ Request gagal: {e} (attempt {attempt})")

            if attempt < settings.scraper_max_retries:
                # Exponential backoff: 2, 4, 8 detik...
                wait_time = 2 ** attempt
                print(f"   ↳ Menunggu {wait_time}s sebelum retry...")
                await asyncio.sleep(wait_time)

        print(f"❌ Gagal mengambil {url} setelah {settings.scraper_max_retries} percobaan.")
        return None

    def _parse_html(self, html: str) -> BeautifulSoup:
        """Helper untuk mem-parsing HTML string menjadi objek BeautifulSoup."""
        return BeautifulSoup(html, "html.parser")

    # =========================================================================
    # Abstract Methods — Harus diimplementasikan oleh setiap subclass
    # =========================================================================

    @abstractmethod
    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        """
        Mengambil daftar URL artikel yang dipublikasikan pada tanggal tertentu
        dari halaman indeks berita portal.

        Args:
            target_date: Tanggal yang ingin di-scrape.

        Returns:
            list[str]: Daftar URL artikel pada tanggal tersebut.
        """
        ...

    @abstractmethod
    async def scrape_article(self, url: str, target_date: date) -> Optional[RawArticle]:
        """
        Mengambil konten lengkap (judul + isi) dari satu URL artikel.

        Args:
            url: URL artikel yang akan di-scrape.
            target_date: Tanggal publikasi artikel.

        Returns:
            RawArticle: Data artikel mentah, atau None jika scraping gagal.
        """
        ...

    # =========================================================================
    # Template Method — Orkestrasi utama scraping (tidak perlu di-override)
    # =========================================================================

    async def scrape_by_date(self, target_date: date) -> list[RawArticle]:
        """
        Template method: mengorkestrasi seluruh proses scraping untuk satu tanggal.
        1. Ambil semua URL dari halaman indeks
        2. Scrape detail setiap artikel

        Args:
            target_date: Tanggal yang ingin di-scrape.

        Returns:
            list[RawArticle]: Daftar artikel yang berhasil di-scrape.
        """
        print(f"\n📰 [{self.source_name.upper()}] Scraping berita tanggal: {target_date}")
        
        # Langkah 1: Ambil semua URL artikel
        urls = await self.get_article_urls_by_date(target_date)
        print(f"   ✅ Ditemukan {len(urls)} URL artikel.")

        if not urls:
            return []

        # Langkah 2: Scrape setiap artikel
        articles: list[RawArticle] = []
        for i, url in enumerate(urls, start=1):
            print(f"   [{i}/{len(urls)}] Scraping: {url}")
            article = await self.scrape_article(url, target_date)
            if article:
                articles.append(article)

        print(f"   🏁 Selesai. {len(articles)}/{len(urls)} artikel berhasil di-scrape.")
        return articles
