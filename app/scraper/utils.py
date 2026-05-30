"""
utils.py (scraper)
------------------
Fungsi-fungsi utilitas untuk scraper:
- Rotasi User-Agent agar request terlihat seperti dari browser berbeda
- Helper untuk parsing tanggal dari berbagai format portal Indonesia
"""

import random
from datetime import date, datetime
from typing import Optional


# Daftar User-Agent dari berbagai browser dan OS populer.
# Rotasi ini membantu menghindari pemblokiran berdasarkan header.
USER_AGENTS = [
    # Chrome di Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome di macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox di Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox di Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari di macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge di Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome di Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
]

# Pemetaan nama bulan dalam bahasa Indonesia ke nomor bulan.
# Dibutuhkan karena portal Indonesia sering menulis tanggal dalam format:
# "15 Januari 2025" atau "15 Jan 2025"
INDONESIAN_MONTHS: dict[str, int] = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "aug": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12, "dec": 12,
}


def get_random_user_agent() -> str:
    """
    Mengembalikan satu User-Agent secara acak dari daftar yang sudah didefinisikan.
    
    Returns:
        str: String User-Agent yang akan digunakan sebagai HTTP header.
    """
    return random.choice(USER_AGENTS)


def parse_indonesian_date(date_string: str) -> Optional[date]:
    """
    Mem-parsing string tanggal dalam format Indonesia menjadi objek `date`.
    
    Format yang didukung:
    - "15 Januari 2025"
    - "15 Jan 2025"
    - "2025-01-15" (ISO format)
    - "15/01/2025"

    Args:
        date_string: String tanggal yang akan di-parse.

    Returns:
        date: Objek tanggal yang sudah di-parse, atau None jika format tidak dikenali.
    """
    date_string = date_string.strip().lower()

    # Coba format ISO (2025-01-15) — umum di metadata/JSON
    try:
        return date.fromisoformat(date_string)
    except ValueError:
        pass

    # Coba format "15 januari 2025" atau "15 jan 2025"
    parts = date_string.split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = INDONESIAN_MONTHS.get(parts[1])
            year = int(parts[2])
            if month:
                return date(year, month, day)
        except (ValueError, TypeError):
            pass

    # Coba format "15/01/2025"
    try:
        return datetime.strptime(date_string, "%d/%m/%Y").date()
    except ValueError:
        pass

    # Coba format "15-01-2025"
    try:
        return datetime.strptime(date_string, "%d-%m-%Y").date()
    except ValueError:
        pass

    return None


def clean_text(text: str) -> str:
    """
    Membersihkan teks dari whitespace berlebih yang sering muncul
    setelah scraping konten HTML.
    
    Args:
        text: Teks mentah hasil scraping.
    
    Returns:
        str: Teks yang sudah dibersihkan.
    """
    # Hapus whitespace di awal/akhir dan normalisasi spasi ganda
    lines = [line.strip() for line in text.splitlines()]
    cleaned = " ".join(line for line in lines if line)
    return cleaned
