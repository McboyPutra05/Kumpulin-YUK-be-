from datetime import date
from typing import Optional

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class KumparanScraper(BaseScraper):
    """
    Scraper untuk portal berita Kumparan.
    Kumparan tidak memiliki indeks berdasarkan tanggal yang eksplisit,
    jadi kita mengambil dari halaman trending/news dan hanya mengambil artikel
    yang relevan dengan tanggal target (jika memungkinkan) atau semua artikel baru.
    """

    source_name = "kumparan"
    BASE_INDEX_URL = "https://kumparan.com/trending"

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        # Kumparan menggunakan trending sebagai basis untuk artikel populer/baru
        all_urls: list[str] = []
        
        # Kita hanya scrape 1 halaman (halaman utama trending) karena infinite scroll
        html = await self._fetch(self.BASE_INDEX_URL)
        if not html:
            return []

        soup = self._parse_html(html)
        
        # Cari link artikel
        article_links = soup.find_all("a", href=True)
        
        found_count = 0
        for a_tag in article_links:
            href = a_tag.get("href", "")
            # Artikel kumparan biasanya punya ID panjang di akhir URL
            # dan bukan halaman kategori/tag (yang biasanya pendek)
            if "/trending" not in href and len(href) > 30 and not href.startswith("https://showcase."):
                full_url = href if href.startswith("http") else f"https://kumparan.com{href}"
                all_urls.append(full_url)
                found_count += 1

        print(f"   📄 Halaman Trending: ditemukan {found_count} URL.")
        return list(dict.fromkeys(all_urls))

    async def scrape_article(self, url: str, target_date: date) -> Optional[RawArticle]:
        html = await self._fetch(url)
        if not html:
            return None

        soup = self._parse_html(html)

        # --- JUDUL ---
        title_tag = soup.select_one("h1")
        if not title_tag:
            return None
        title = clean_text(title_tag.get_text())

        # --- KONTEN ---
        # Kumparan menggunakan div dengan data-qa-id="article-body" 
        # atau class khusus untuk paragraph wrapper
        content_div = soup.find("div", attrs={"data-qa-id": "article-body"})
        
        if not content_div:
            # Fallback ke semua span dengan article-body-text
            paragraphs = soup.find_all("span", attrs={"data-qa-id": "article-body-text"})
            if not paragraphs:
                paragraphs = soup.find_all("div", class_="components__ParagraphWrapper-sc-1l0yymu-0")
        else:
            paragraphs = content_div.find_all("span", attrs={"data-qa-id": "article-body-text"})
            if not paragraphs:
                paragraphs = content_div.find_all("p")

        content = clean_text(" ".join(p.get_text() for p in paragraphs))

        if not content or len(content) < 50:
            return None

        return RawArticle(
            title=title,
            url=url,
            source=self.source_name,
            published_date=target_date,  # Kumparan tidak memberikan tgl secara mudah di DOM
            content=content,
        )
