"""
article_generator.py
--------------------
Service untuk generate artikel berita lengkap dari data scraping
menggunakan Google Gemini API dan prompt expert jurnalis profesional.

Menggunakan pola "lazy initialization" yang sama dengan summarizer.py.
"""

import google.generativeai as genai
from app.config import settings


class ArticleGeneratorService:
    """
    Service wrapper untuk Google Gemini API.
    Bertugas menghasilkan artikel berita lengkap berkualitas jurnalistik
    dari data artikel hasil scraping, menggunakan prompt expert yang telah dikonfigurasi.
    """

    # Prompt expert penulis berita profesional bergaya Kompas.com
    ARTICLE_PROMPT_TEMPLATE = """# PROMPT EXPERT PENULIS BERITA PROFESIONAL

Anda adalah jurnalis media nasional berpengalaman yang menulis berita dengan gaya penulisan serupa Kompas.com.

Tugas Anda adalah membuat artikel berita berdasarkan informasi yang diberikan.

## Aturan Penulisan Judul

Buat judul yang:

* Ringkas dan informatif.
* Fokus pada fakta paling penting.
* Tidak menggunakan clickbait.
* Tidak menggunakan opini atau spekulasi.
* Panjang ideal 8-15 kata.
* Mengandung unsur peristiwa utama yang menjadi inti berita.

## Struktur Artikel

### Paragraf 1 (Lead)

Tulis ringkasan peristiwa paling penting dalam 1 paragraf.

Paragraf ini harus langsung menjawab sebagian besar unsur:

* Apa yang terjadi
* Di mana terjadi
* Siapa yang terlibat
* Kapan terjadi
* Tindakan atau perkembangan terbaru

### Paragraf 2 dan Seterusnya

Kembangkan informasi dengan pola berikut:

1. Keterangan pejabat, narasumber, saksi, atau pihak terkait.
2. Kutipan langsung yang relevan.
3. Penjelasan tambahan mengenai kondisi atau perkembangan kasus/peristiwa.
4. Informasi hasil penyelidikan, investigasi, keputusan, atau tindak lanjut.
5. Kronologi kejadian.
6. Keterangan saksi atau pihak yang pertama mengetahui peristiwa.

## Gaya Bahasa

* Gunakan bahasa Indonesia formal jurnalistik.
* Objektif dan netral.
* Hindari opini penulis.
* Hindari kata-kata sensasional.
* Gunakan kalimat yang jelas dan mudah dipahami.
* Gunakan paragraf pendek.
* Sertakan jabatan narasumber saat pertama kali disebut.
* Gunakan kutipan langsung seperlunya untuk memperkuat informasi.

## Format Kutipan

Contoh:

Kepala Dinas Kesehatan Kota Bandung, Budi Santoso, mengatakan bahwa pihaknya masih melakukan pendataan.

"Kami masih mengumpulkan data dari seluruh puskesmas untuk memastikan kondisi sebenarnya," kata Budi, Senin (20/7/2026).

## Output yang Diharapkan

Hasil akhir harus berupa artikel berita utuh yang terdiri dari:

* Judul
* Isi berita lengkap
* Struktur piramida terbalik
* Kutipan narasumber
* Kronologi bila tersedia

## Data Berita

{article_data}

## Instruksi Tambahan

Jika terdapat informasi yang belum lengkap, jangan membuat fakta baru. Gunakan hanya data yang tersedia dan susun menjadi artikel berita profesional yang faktual, padat, dan mudah dipahami.
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
            # Gunakan Gemini Flash untuk keseimbangan kecepatan & kualitas
            self._model = genai.GenerativeModel("gemini-2.5-flash")
        return self._model

    def _build_article_data(self, article_doc: dict) -> str:
        """
        Memformat dokumen artikel MongoDB menjadi teks terstruktur
        yang mudah dipahami oleh Gemini.
        """
        lines = []

        lines.append(f"Judul Asli: {article_doc.get('title', '-')}")
        lines.append(f"Sumber Portal: {article_doc.get('source', '-').capitalize()}")
        lines.append(f"Tanggal Publikasi: {article_doc.get('published_date', '-')}")
        lines.append(f"URL Asli: {article_doc.get('url', '-')}")
        lines.append("")
        lines.append("Isi Artikel Asli:")
        lines.append("---")
        lines.append(article_doc.get("content", "Konten tidak tersedia."))

        if article_doc.get("summary"):
            lines.append("")
            lines.append("Ringkasan Singkat:")
            lines.append(article_doc["summary"])

        return "\n".join(lines)

    async def generate(self, article_doc: dict) -> str:
        """
        Menghasilkan artikel berita lengkap dari dokumen artikel mentah.

        Args:
            article_doc: Dokumen artikel MongoDB (raw dict) yang berisi
                         title, content, source, published_date, dll.

        Returns:
            str: Artikel berita lengkap hasil generate AI.

        Raises:
            ValueError: Jika API key tidak dikonfigurasi.
            Exception: Jika terjadi error dari Gemini API.
        """
        model = self._get_model()

        # Batasi panjang content untuk menghindari token limit
        # Gemini Flash punya konteks panjang, tapi 5000 karakter cukup untuk berita
        content = article_doc.get("content", "")
        max_content_length = 5000
        if len(content) > max_content_length:
            article_doc = {**article_doc, "content": content[:max_content_length] + "..."}

        article_data_text = self._build_article_data(article_doc)
        prompt = self.ARTICLE_PROMPT_TEMPLATE.format(article_data=article_data_text)

        # Panggil Gemini API secara async
        response = await model.generate_content_async(prompt)

        generated_text = response.text.strip()
        return generated_text


# Instance singleton yang bisa diimpor langsung
article_generator_service = ArticleGeneratorService()
