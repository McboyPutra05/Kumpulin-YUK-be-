"""
detik.py
--------
Implementasi scraper untuk Detik.com.

URL pencarian berdasarkan tanggal:
  https://www.detik.com/search/searchall?query=&siteid=3&sortby=time&types=artikel&date=DD/MM/YYYY

Selector telah diverifikasi terhadap HTML aktual Detik.com (Mei 2025).

CATATAN: Detik.com memiliki banyak sub-portal (news, finance, sport, dsb.).
Scraper ini fokus pada kanal berita utama melalui endpoint search.
"""

from datetime import date
from typing import Optional

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class DetikScraper(BaseScraper):
    """
    Scraper untuk portal berita Detik.com.

    Strategi: Gunakan endpoint pencarian Detik yang mendukung filter tanggal
    untuk mendapatkan semua artikel pada tanggal tertentu.
    """

    source_name = "detik"
    BASE_SEARCH_URL = "https://www.detik.com/search/searchall"

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        """
        Mengambil URL artikel dari hasil pencarian Detik yang difilter berdasarkan tanggal.
        """
        # Format tanggal Detik: DD/MM/YYYY
        date_str = target_date.strftime("%d/%m/%Y")
        all_urls: list[str] = []
        page = 1

        while True:
            search_url = (
                f"{self.BASE_SEARCH_URL}"
                f"?query=&siteid=3&sortby=time&types=artikel&date={date_str}&page={page}"
            )
            html = await self._fetch(search_url)

            if not html:
                break

            soup = self._parse_html(html)

            # Selector utama: kartu artikel di halaman search results Detik
            # Struktur aktual: <article class="list-content__item"> > <a class="media__link">
            article_links = soup.select("article.list-content__item .media__link")

            # Fallback: coba selector alternatif jika struktur berubah
            if not article_links:
                article_links = soup.select(".list-content__item a[href*='detik.com']")

            if not article_links:
                # Coba selector yang lebih lebar
                article_links = soup.select("article a[href*='detik.com']")

            if not article_links:
                print(f"   ℹ️ Tidak ada hasil di halaman {page}, berhenti.")
                break

            found_count = 0
            for a_tag in article_links:
                href = a_tag.get("href", "")
                if href and href.startswith("http") and "detik.com" in href:
                    # Filter: hindari URL navigasi (kategori, tag, dsb.)
                    if any(skip in href for skip in ["/tag/", "/kategori/", "search"]):
                        continue
                    all_urls.append(href)
                    found_count += 1

            print(f"   📄 Halaman {page}: ditemukan {found_count} URL.")
            page += 1

            if page > 50:
                break

        return list(dict.fromkeys(all_urls))

    async def scrape_article(self, url: str, target_date: date) -> Optional[RawArticle]:
        """
        Mengambil judul dan konten lengkap dari satu URL artikel Detik.
        """
        html = await self._fetch(url)
        if not html:
            return None

        soup = self._parse_html(html)

        # --- JUDUL ---
        # Detik menggunakan <h1 class="detail__title"> pada halaman artikel
        title_tag = (
            soup.select_one("h1.detail__title")
            or soup.select_one("h1.itp_title")
            or soup.select_one("h1")
        )
        if not title_tag:
            return None
        title = clean_text(title_tag.get_text())

        # --- KONTEN ---
        # Detik menyimpan body artikel di <div class="detail__body-text itp_bodycontent">
        content_div = (
            soup.select_one("div.detail__body-text")
            or soup.select_one("div.itp_bodycontent")
            or soup.select_one("div[class*='detail__body']")
        )
        if not content_div:
            return None

        # Hapus elemen tidak relevan (iklan, related articles)
        for unwanted in content_div.select(
            "div.detail__body-tag, div.ads, .ads-placeholder, "
            ".inread, script, style, .googletag"
        ):
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
