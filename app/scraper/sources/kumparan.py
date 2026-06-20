from datetime import date
from typing import Optional
import re

from app.scraper.base_scraper import BaseScraper, RawArticle
from app.scraper.utils import clean_text


class KumparanScraper(BaseScraper):
    """
    Scraper untuk portal berita Kumparan.

    Kumparan menggunakan client-side rendering (React/Apollo) untuk halaman
    /channel/*, sehingga artikel TIDAK tersedia di HTML server-rendered.

    Solusi: scrape dari halaman publisher (kumparannews, kumparanbisnis, dll)
    yang memiliki SSR (server-side rendered) artikel links.
    Setiap halaman publisher menghasilkan ~10 artikel unik.
    """

    source_name = "kumparan"

    # Halaman publisher yang memiliki artikel SSR (server-rendered)
    # Setiap halaman menghasilkan ~10 artikel terbaru
    PUBLISHER_PAGES = [
        "https://kumparan.com/kumparannews",
        "https://kumparan.com/kumparanbisnis",
        "https://kumparan.com/kumparantech",
        "https://kumparan.com/kumparanhits",
        "https://kumparan.com/kumparansains",
        "https://kumparan.com/kumparanfood",
        "https://kumparan.com/kumparanmom",
        "https://kumparan.com/kumparanoto",
        "https://kumparan.com/kumparantravel",
    ]

    # Pattern URL artikel kumparan: /kumparanXXX/judul-artikel-HASHID
    # Contoh: /kumparannews/kata-kapolri-soal-penangkapan-27dMf6EqCKI
    ARTICLE_URL_PATTERN = re.compile(
        r"^/kumparan[a-z]+/.+-[a-zA-Z0-9]{8,}$"
    )

    async def get_article_urls_by_date(self, target_date: date) -> list[str]:
        all_urls: list[str] = []

        for page_url in self.PUBLISHER_PAGES:
            html = await self._fetch(page_url)
            if not html:
                continue

            soup = self._parse_html(html)
            article_links = soup.find_all("a", href=True)

            page_count = 0
            for a_tag in article_links:
                href = a_tag.get("href", "")

                # Normalisasi: ambil path saja jika full URL
                if href.startswith("https://kumparan.com"):
                    href = href.replace("https://kumparan.com", "")

                # Hanya ambil URL yang cocok pola artikel kumparan
                if self.ARTICLE_URL_PATTERN.match(href):
                    full_url = f"https://kumparan.com{href}"
                    if full_url not in all_urls:
                        all_urls.append(full_url)
                        page_count += 1

            category = page_url.split("/")[-1]
            print(f"   [Page] {category}: ditemukan {page_count} URL artikel baru.")

        print(f"   [Total] Total: {len(all_urls)} URL artikel unik dari semua kategori.")
        return all_urls

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
        # Kumparan menggunakan <main class="StoryRenderer__EditorWrapper-...">
        # dengan paragraf (<p>) di dalamnya sebagai container konten artikel.
        content_main = soup.find("main", class_=re.compile(r"StoryRenderer"))

        if content_main:
            paragraphs = content_main.find_all("p")
        else:
            # Fallback: cari <main> tag biasa
            main_tag = soup.find("main")
            if main_tag:
                paragraphs = main_tag.find_all("p")
            else:
                # Fallback terakhir: cari div dengan data-qa-id lama (backward compat)
                content_div = soup.find("div", attrs={"data-qa-id": "article-body"})
                if content_div:
                    paragraphs = content_div.find_all("p")
                else:
                    paragraphs = []

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
