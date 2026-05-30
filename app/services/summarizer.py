"""
summarizer.py
-------------
Service untuk meringkas teks artikel menggunakan Google Gemini API.

Menggunakan pola "lazy initialization" — client hanya dibuat saat pertama kali dibutuhkan.
Ini menghindari error di environment development yang belum mengatur API key.
"""

import google.generativeai as genai
from app.config import settings


class SummarizerService:
    """
    Service wrapper untuk Google Gemini API.
    Bertugas menghasilkan ringkasan 1 paragraf dari teks artikel.
    """

    # Prompt yang di-engineering untuk menghasilkan ringkasan berkualitas tinggi
    SUMMARY_PROMPT_TEMPLATE = """
Kamu adalah asisten AI yang ahli dalam merangkum berita.

Tugas kamu: Baca teks artikel berita berikut dan tulis RINGKASAN dalam SATU paragraf yang:
- Mencakup 5W+1H (Who, What, When, Where, Why, How) jika tersedia
- Ditulis dalam Bahasa Indonesia yang baku dan mudah dipahami
- Panjang antara 3-5 kalimat
- Objektif dan tidak menambahkan opini

Artikel:
---
{article_content}
---

Ringkasan:
"""

    def __init__(self):
        self._model = None

    def _get_model(self):
        """
        Inisialisasi lazy untuk Gemini model.
        Akan error dengan pesan yang jelas jika API key belum diset.
        """
        if self._model is None:
            if not settings.gemini_api_key:
                raise ValueError(
                    "GEMINI_API_KEY belum diatur di file .env! "
                    "Dapatkan API key di: https://aistudio.google.com/"
                )
            genai.configure(api_key=settings.gemini_api_key)
            # Gunakan model Gemini Flash untuk efisiensi biaya & kecepatan
            self._model = genai.GenerativeModel("gemini-1.5-flash")
        return self._model

    async def summarize(self, article_content: str) -> str:
        """
        Meringkas konten artikel menggunakan Gemini API.

        Args:
            article_content: Teks lengkap artikel yang akan diringkas.

        Returns:
            str: Ringkasan artikel dalam 1 paragraf.

        Raises:
            ValueError: Jika API key tidak dikonfigurasi.
            Exception: Jika terjadi error dari Gemini API.
        """
        model = self._get_model()

        # Batasi panjang konten untuk menghindari token limit dan biaya berlebih.
        # Gemini Flash mendukung konteks panjang, tapi untuk berita 3000 karakter sudah cukup.
        max_content_length = 3000
        truncated_content = article_content[:max_content_length]
        if len(article_content) > max_content_length:
            truncated_content += "..."

        prompt = self.SUMMARY_PROMPT_TEMPLATE.format(article_content=truncated_content)

        # Panggil API secara async menggunakan generate_content_async
        response = await model.generate_content_async(prompt)
        
        summary = response.text.strip()
        return summary

    async def summarize_batch(
        self,
        articles: list[dict],
        id_field: str = "_id",
        content_field: str = "content",
    ) -> dict[str, str]:
        """
        Meringkas banyak artikel sekaligus.
        Mengembalikan dictionary {article_id: summary}.

        Args:
            articles: Daftar dokumen artikel dari MongoDB.
            id_field: Nama field ID dokumen.
            content_field: Nama field konten artikel.

        Returns:
            dict: Mapping dari article_id ke ringkasan.
        """
        summaries: dict[str, str] = {}

        for article in articles:
            article_id = str(article.get(id_field, ""))
            content = article.get(content_field, "")

            if not content:
                continue

            try:
                summary = await self.summarize(content)
                summaries[article_id] = summary
                print(f"   ✅ Artikel {article_id[:8]}... berhasil diringkas.")
            except Exception as e:
                print(f"   ❌ Gagal meringkas artikel {article_id[:8]}...: {e}")
                summaries[article_id] = "Ringkasan tidak tersedia."

        return summaries


# Instance singleton yang bisa diimpor langsung
summarizer_service = SummarizerService()
