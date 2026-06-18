from datetime import date
from typing import Optional

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class Liputan6Scraper(BaseScraper):
    """
    Scraper untuk portal berita Liputan6.
    """

    source_name = "liputan6"
    BASE_INDEX_URL = "https://www.liputan6.com/indeks"

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        date_str = target_date.strftime("%Y/%m/%d")
        all_urls: list[str] = []
        page = 1

        while True:
            # Contoh URL: https://www.liputan6.com/indeks/2026/06/18?page=1
            index_url = f"{self.BASE_INDEX_URL}/{date_str}?page={page}"
            html = await self._fetch(index_url)

            if not html:
                break

            soup = self._parse_html(html)
            
            # Cari link artikel di indeks
            article_links = soup.select("a[href*='liputan6.com']")
            
            found_count = 0
            for a_tag in article_links:
                href = a_tag.get("href", "")
                if href and len(href) > 40 and "/read/" in href:
                    all_urls.append(href)
                    found_count += 1

            print(f"   📄 Halaman {page}: ditemukan {found_count} URL.")
            
            if found_count == 0:
                break
                
            page += 1
            if page > 50:
                break

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
        content_div = (
            soup.select_one("div.article-content-body__item-content")
            or soup.select_one("div[class*='article-content-body']")
        )
        
        if not content_div:
            return None

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
