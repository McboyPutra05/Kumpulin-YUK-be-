"""
tempo.py
--------
Implementasi scraper untuk Tempo.co.

URL Indeks berdasarkan tanggal (DIVERIFIKASI Mei 2025):
  https://www.tempo.co/indeks?date=YYYY-MM-DD

CATATAN PENTING:
- Halaman indeks Tempo menggunakan JavaScript rendering untuk memuat daftar artikel.
  Scraper dengan httpx (HTML statis) mungkin tidak mendapatkan semua artikel.
  Jika hasilnya kosong, perlu beralih ke Playwright (browser headless).
- Tempo memiliki paywall ("Tempo Plus") — artikel premium hanya menampilkan beberapa paragraf.
"""

from datetime import date
from typing import Optional

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class TempoScraper(BaseScraper):
    """
    Scraper untuk portal berita Tempo.co.

    Strategi:
    1. Akses halaman indeks dengan query param ?date=YYYY-MM-DD
    2. Ekstrak URL artikel menggunakan selector yang sudah diverifikasi
    3. Scrape konten setiap artikel
    """

    source_name = "tempo"
    BASE_INDEX_URL = "https://www.tempo.co/indeks"

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        """
        Mengambil URL artikel dari halaman indeks harian Tempo.

        URL format yang benar (diverifikasi): ?date=YYYY-MM-DD
        (bukan /indeks/YYYY/MM/DD — itu menghasilkan 404)
        """
        date_str = target_date.strftime("%Y-%m-%d")
        all_urls: list[str] = []
        page = 1

        while True:
            # Format URL yang sudah diverifikasi
            index_url = f"{self.BASE_INDEX_URL}?date={date_str}&page={page}"
            html = await self._fetch(index_url)

            if not html:
                break

            soup = self._parse_html(html)

            # Selector utama (diverifikasi via inspeksi browser):
            # Link artikel menggunakan aria-label yang dimulai dengan "Baca artikel:"
            article_links = soup.select("a[aria-label^='Baca artikel:']")

            # Fallback 1: link dengan class hover:opacity-75 (class Tailwind di Tempo)
            if not article_links:
                # Escape backslash untuk BeautifulSoup CSS selector
                article_links = soup.select("a.hover\\:opacity-75[href*='tempo.co']")

            # Fallback 2: link di dalam heading artikel
            if not article_links:
                article_links = soup.select("h2 > a[href*='tempo.co'], h3 > a[href*='tempo.co']")

            if not article_links:
                print(f"   ℹ️ Tidak ada artikel di halaman {page}, berhenti iterasi.")
                print(f"   💡 Catatan: Tempo.co membutuhkan JavaScript rendering.")
                print(f"      Pertimbangkan Playwright jika hasil selalu kosong.")
                break

            found_count = 0
            for a_tag in article_links:
                href = a_tag.get("href", "")
                if not href:
                    continue
                # Normalisasi URL relatif
                if href.startswith("/"):
                    href = f"https://www.tempo.co{href}"
                if "tempo.co" in href and href.startswith("http"):
                    all_urls.append(href)
                    found_count += 1

            print(f"   📄 Halaman {page}: ditemukan {found_count} URL.")

            # Cek apakah ada halaman berikutnya
            # Tempo menggunakan ?page=N sebagai query param
            page += 1
            if page > 20:  # Lebih konservatif untuk Tempo
                break

        return list(dict.fromkeys(all_urls))

    async def scrape_article(self, url: str, target_date: date) -> Optional[RawArticle]:
        """
        Mengambil judul dan konten lengkap dari satu URL artikel Tempo.
        """
        html = await self._fetch(url)
        if not html:
            return None

        soup = self._parse_html(html)

        # --- JUDUL ---
        # Tempo menggunakan <h1> sebagai judul utama artikel
        title_tag = soup.select_one("h1")
        if not title_tag:
            return None
        title = clean_text(title_tag.get_text())

        # --- KONTEN ---
        # Tempo menyimpan body artikel di <div class="detail-in">
        content_div = (
            soup.select_one("div.detail-in")
            or soup.select_one("div[class*='detail-in']")
            or soup.select_one("div.article-content")
        )

        if not content_div:
            # Fallback: cari section yang mengandung banyak paragraf
            all_divs = soup.find_all("div")
            best_div = max(
                all_divs,
                key=lambda d: len(d.find_all("p")),
                default=None,
            )
            if best_div and len(best_div.find_all("p")) >= 3:
                content_div = best_div

        if not content_div:
            return None

        # Bersihkan elemen tidak relevan
        for unwanted in content_div.select(
            "div.read-next, div.tempo-plus, button, "
            "div[class*='paywall'], div[class*='subscribe'], script, style"
        ):
            unwanted.decompose()

        paragraphs = content_div.find_all("p")
        content = clean_text(" ".join(p.get_text() for p in paragraphs))

        # Tempo paywall: konten terlalu pendek = artikel premium
        if not content or len(content) < 50:
            print(f"   ⚠️ Konten terlalu pendek (mungkin paywall): {url[:60]}")
            return None

        return RawArticle(
            title=title,
            url=url,
            source=self.source_name,
            published_date=target_date,
            content=content,
        )
