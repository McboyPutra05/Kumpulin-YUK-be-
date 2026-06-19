"""
kompas.py
---------
Implementasi scraper untuk Kompas.com.

URL Indeks berdasarkan tanggal:
  https://indeks.kompas.com/?site=all&date=YYYY-MM-DD&page=1

Selector telah diverifikasi terhadap HTML aktual Kompas.com (Mei 2025).
Jika scraper berhenti bekerja, periksa kembali selector menggunakan
DevTools browser (F12 > Inspect Element).
"""

from datetime import date
from typing import Optional

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class KompasScraper(BaseScraper):
    """
    Scraper untuk portal berita Kompas.com.

    Strategi:
    1. Iterasi halaman indeks (?page=1, ?page=2, dst.) hingga tidak ada artikel lagi.
    2. Kumpulkan semua URL artikel dari semua halaman.
    3. Scrape konten setiap URL satu per satu.
    """

    source_name = "kompas"
    BASE_INDEX_URL = "https://indeks.kompas.com/"

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        """
        Mengambil semua URL artikel dari halaman indeks Kompas untuk tanggal tertentu.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        all_urls: list[str] = []
        page = 1

        while True:
            index_url = f"{self.BASE_INDEX_URL}?site=all&date={date_str}&page={page}"
            html = await self._fetch(index_url)

            if not html:
                print(f"   [!] Halaman {page} tidak dapat diakses, berhenti.")
                break

            soup = self._parse_html(html)

            # Selector utama: link artikel di halaman indeks Kompas
            # Struktur: <div class="articleItem"> <a class="articleItem--link" href="...">
            article_links = soup.select("a.articleItem--link")

            # Fallback: coba selector alternatif
            if not article_links:
                article_links = soup.select(".articleList a[href*='kompas.com']")

            if not article_links:
                print(f"   [Info] Tidak ada artikel di halaman {page}, berhenti iterasi.")
                break

            found_count = 0
            for a_tag in article_links:
                href = a_tag.get("href", "")
                if href and href.startswith("http") and "kompas.com" in href:
                    all_urls.append(href)
                    found_count += 1

            print(f"   [Page] Halaman {page}: ditemukan {found_count} URL.")
            page += 1

            if page > 50:
                print("   [!] Batas maksimal halaman (50) tercapai.")
                break

        return list(dict.fromkeys(all_urls))

    async def scrape_article(self, url: str, target_date: date) -> Optional[RawArticle]:
        """
        Mengambil judul dan konten lengkap dari satu URL artikel Kompas.
        """
        html = await self._fetch(url)
        if not html:
            return None

        soup = self._parse_html(html)

        # --- JUDUL ---
        # Kompas menggunakan <h1 class="read__title"> pada halaman artikel
        title_tag = (
            soup.select_one("h1.read__title")
            or soup.select_one("h1.article__title")
            or soup.select_one("h1")
        )
        if not title_tag:
            print(f"   [!] Judul tidak ditemukan di: {url}")
            return None
        title = clean_text(title_tag.get_text())

        # --- KONTEN ---
        # Kompas menyimpan body artikel di <div class="read__content">
        content_div = (
            soup.select_one("div.read__content")
            or soup.select_one("div.article__content")
            or soup.select_one("div[class*='read__content']")
        )
        if not content_div:
            print(f"   [!] Konten tidak ditemukan di: {url}")
            return None

        # Ambil semua paragraf, hilangkan elemen iklan/promo
        for unwanted in content_div.select("div.ads-placeholder, div.google-auto-placed, .baca-juga"):
            unwanted.decompose()

        paragraphs = content_div.find_all("p")
        content = clean_text(" ".join(p.get_text() for p in paragraphs))

        if not content or len(content) < 50:
            return None

        return RawArticle(
            title=title,
            url=url,
            source=self.source_name,
            published_date=target_date,
            content=content,
        )
