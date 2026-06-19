"""
summarizer.py
-------------
Service untuk meringkas teks artikel menggunakan Google Gemini API.
Menggunakan pendekatan yang identik dengan article_generator.py (SDK genai)
agar konsisten dan kompatibel dengan token yang sama.

Dilengkapi retry + exponential backoff untuk menangani rate limit.
"""

import asyncio
import json
import re
import google.generativeai as genai
from app.config import settings

# --- Konfigurasi Rate Limit ---
DELAY_BETWEEN_REQUESTS = 2.0   # detik jeda sebelum request (untuk single manual request)
MAX_RETRIES = 3                 # maksimal percobaan ulang saat rate limit
RETRY_BASE_DELAY = 15.0        # detik jeda awal saat kena 429

# Model yang digunakan (sama dengan article_generator.py)
GEMINI_MODEL = "gemini-2.5-flash"


class SummarizerService:
    """
    Service wrapper untuk Google Gemini API.
    Bertugas menghasilkan ringkasan singkat + 4 tag SEO dari teks artikel.

    Menggunakan pendekatan SDK yang sama persis dengan ArticleGeneratorService
    agar token/credential yang dipakai konsisten.
    """

    # Prompt untuk menghasilkan ringkasan + tag SEO
    SUMMARY_PROMPT_TEMPLATE = """
Kamu adalah asisten AI yang ahli dalam merangkum berita dan optimasi SEO Google.

Tugas kamu: Baca teks artikel berita berikut, lalu hasilkan output dalam format JSON yang berisi:
1. "summary": Ringkasan singkat MAKSIMAL 140 karakter yang:
   - Mencakup inti berita (Who, What, When/Where) secara padat
   - Ditulis dalam Bahasa Indonesia yang baku dan mudah dipahami
   - Objektif, tidak berisi opini, tidak menggunakan clickbait
   - Wajib kurang dari atau sama dengan 140 karakter
2. "tags": Array berisi TEPAT 4 tag/kata kunci yang:
   - Merepresentasikan topik utama artikel
   - Dioptimalkan untuk SEO Google (gunakan kata kunci yang banyak dicari)
   - Ditulis dalam Bahasa Indonesia, huruf kecil semua
   - Singkat (1-3 kata per tag)

Artikel:
---
{article_content}
---

Output hanya berupa JSON valid tanpa markdown code block, contoh format:
{{"summary": "Ringkasan singkat di sini maksimal 140 karakter.", "tags": ["tag satu", "tag dua", "tag tiga", "tag empat"]}}
"""

    def __init__(self):
        self._model = None

    def _get_model(self):
        """
        Inisialisasi lazy untuk Gemini model.
        Identik dengan ArticleGeneratorService._get_model() agar
        konsisten menggunakan credential yang sama.
        """
        if self._model is None:
            if not settings.gemini_api_key:
                raise ValueError(
                    "GEMINI_API_KEY belum diatur di file .env! "
                    "Dapatkan API key di: https://aistudio.google.com/"
                )
            genai.configure(api_key=settings.gemini_api_key)
            self._model = genai.GenerativeModel(GEMINI_MODEL)
        return self._model

    def _parse_response(self, raw: str) -> tuple[str, list[str]]:
        """
        Parse teks respons Gemini menjadi (summary, tags).
        Membersihkan markdown code block jika ada, lalu parse JSON.
        """
        # Bersihkan markdown code block (```json ... ```)
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"```\s*$", "", raw)
        raw = raw.strip()

        try:
            data = json.loads(raw)
            summary = str(data.get("summary", "")).strip()[:140]
            tags = [str(t).strip().lower() for t in data.get("tags", [])[:4]]
            # Pastikan selalu ada tepat 4 tag
            while len(tags) < 4:
                tags.append("berita")
            return summary, tags
        except (json.JSONDecodeError, AttributeError):
            # Fallback: pakai raw text sebagai summary
            return raw[:140], ["berita", "indonesia", "nasional", "terkini"]

    async def summarize(self, article_content: str) -> tuple[str, list[str]]:
        """
        Meringkas konten artikel dengan retry + exponential backoff.

        Args:
            article_content: Teks lengkap artikel yang akan diringkas.

        Returns:
            tuple: (summary: str, tags: list[str])

        Raises:
            Exception: Jika semua percobaan retry gagal.
        """
        model = self._get_model()

        # Potong konten agar tidak melebihi batas token
        max_content_length = 3000
        truncated_content = article_content[:max_content_length]
        if len(article_content) > max_content_length:
            truncated_content += "..."

        prompt = self.SUMMARY_PROMPT_TEMPLATE.format(article_content=truncated_content)

        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

                # Panggil Gemini API — identik dengan cara article_generator.py
                response = await model.generate_content_async(prompt)

                # Cek apakah response diblokir safety filter atau kosong
                if not response.candidates:
                    raise ValueError(
                        "Gemini API mengembalikan response kosong (tidak ada candidates). "
                        "Kemungkinan konten diblokir oleh safety filter."
                    )

                # Cek apakah candidate pertama memiliki content/text
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason') and candidate.finish_reason not in (None, 1):
                    # finish_reason: 1 = STOP (normal), lainnya = SAFETY/MAX_TOKENS/dll
                    finish_reason_name = getattr(candidate.finish_reason, 'name', str(candidate.finish_reason))
                    if finish_reason_name == "SAFETY":
                        raise ValueError(
                            f"Response diblokir oleh safety filter (finish_reason={finish_reason_name})."
                        )

                raw_text = response.text.strip()
                return self._parse_response(raw_text)

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                is_rate_limit = (
                    "429" in str(e)
                    or "resource_exhausted" in error_str
                    or "rate limit" in error_str
                    or "quota" in error_str
                    or "too many requests" in error_str
                )

                if attempt < MAX_RETRIES:
                    if is_rate_limit:
                        wait_time = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        print(
                            f"   [Retry] Rate limit! Percobaan {attempt}/{MAX_RETRIES}. "
                            f"Menunggu {wait_time:.0f} detik..."
                        )
                    else:
                        wait_time = RETRY_BASE_DELAY * (2 ** (attempt - 1)) / 2
                        print(
                            f"   [Retry] Error: {str(e)[:100]}. "
                            f"Percobaan {attempt}/{MAX_RETRIES}. "
                            f"Menunggu {wait_time:.0f} detik..."
                        )
                    await asyncio.sleep(wait_time)
                else:
                    print(
                        f"   [Failed] Semua {MAX_RETRIES} percobaan gagal. "
                        f"Error terakhir: {str(e)[:150]}"
                    )

        # Semua retry gagal — return fallback daripada raise exception
        print("   [Fallback] Menggunakan ringkasan default karena API gagal.")
        return (
            "Ringkasan tidak tersedia.",
            ["berita", "indonesia", "nasional", "terkini"],
        )

    async def summarize_batch(
        self,
        articles: list[dict],
        id_field: str = "_id",
        content_field: str = "content",
    ) -> dict[str, tuple[str, list[str]]]:
        """
        Meringkas banyak artikel sekaligus.
        Mengembalikan dictionary {article_id: (summary, tags)}.
        """
        results: dict[str, tuple[str, list[str]]] = {}

        for article in articles:
            article_id = str(article.get(id_field, ""))
            content = article.get(content_field, "")

            if not content:
                continue

            try:
                summary, tags = await self.summarize(content)
                results[article_id] = (summary, tags)
                print(f"   Artikel {article_id[:8]}... berhasil diringkas.")
            except Exception as e:
                print(f"   Gagal meringkas artikel {article_id[:8]}...: {e}")
                results[article_id] = (
                    "Ringkasan tidak tersedia.",
                    ["berita", "indonesia", "nasional", "terkini"],
                )

        return results


# Instance singleton yang bisa diimpor langsung
summarizer_service = SummarizerService()
