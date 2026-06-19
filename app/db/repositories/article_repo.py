"""
article_repo.py
---------------
Repository layer untuk operasi CRUD artikel di MongoDB.
Memisahkan logika database dari business logic (Service layer).
Menggunakan pattern Repository untuk kemudahan testing dan substitusi DB.
"""

from datetime import date
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pymongo import DESCENDING

from app.models.article import ArticleCreate, ArticleUpdate


COLLECTION_NAME = "articles"


class ArticleRepository:
    """
    Menangani semua operasi database untuk koleksi 'articles'.
    
    Setiap method adalah async karena Motor driver menggunakan asyncio.
    """

    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database[COLLECTION_NAME]

    async def create_indexes(self) -> None:
        """
        Membuat index pada koleksi untuk mempercepat query yang sering digunakan.
        Dipanggil sekali saat aplikasi startup.
        """
        # Index pada tanggal dan sumber (kombinasi paling sering difilter)
        await self.collection.create_index([("published_date", DESCENDING)])
        await self.collection.create_index([("source", 1)])
        await self.collection.create_index([("url", 1)], unique=True)  # Mencegah duplikasi
        print("[OK] MongoDB indexes created for 'articles' collection.")

    async def insert_one(self, article_data: ArticleCreate) -> str:
        """
        Menyimpan satu artikel baru ke database.
        
        Returns:
            str: ID dokumen yang baru dibuat.
        """
        doc = article_data.model_dump()
        # Konversi field `date` ke string agar tersimpan konsisten di MongoDB
        doc["published_date"] = str(doc["published_date"])
        
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def insert_many(self, articles: list[ArticleCreate]) -> list[str]:
        """
        Menyimpan banyak artikel sekaligus (bulk insert) — lebih efisien daripada
        insert_one berulang untuk volume besar.

        Returns:
            list[str]: Daftar ID dokumen yang berhasil dibuat.
        """
        docs = []
        for article in articles:
            doc = article.model_dump()
            doc["published_date"] = str(doc["published_date"])
            docs.append(doc)

        result = await self.collection.insert_many(docs, ordered=False)
        return [str(oid) for oid in result.inserted_ids]

    async def find_by_id(self, article_id: str) -> Optional[dict]:
        """
        Mencari satu artikel berdasarkan ID-nya.

        Returns:
            dict | None: Dokumen artikel, atau None jika tidak ditemukan.
        """
        if not ObjectId.is_valid(article_id):
            return None
        return await self.collection.find_one({"_id": ObjectId(article_id)})

    async def find_by_url(self, url: str) -> Optional[dict]:
        """
        Mengecek apakah artikel dengan URL tertentu sudah ada di database.
        Digunakan untuk mencegah duplikasi saat scraping.
        """
        return await self.collection.find_one({"url": url})

    async def find_many(
        self,
        published_date: Optional[date] = None,
        source: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[dict], int]:
        """
        Mengambil daftar artikel dengan filter dan pagination.

        Args:
            published_date: Filter berdasarkan tanggal (opsional).
            source: Filter berdasarkan portal sumber (opsional).
            page: Nomor halaman (mulai dari 1).
            limit: Jumlah artikel per halaman.

        Returns:
            tuple: (list dokumen, total count yang cocok filter)
        """
        # Membangun query filter secara dinamis
        query: dict = {}
        if published_date:
            query["published_date"] = str(published_date)
        if source:
            query["source"] = source.lower()

        # Hitung total dokumen yang cocok (untuk pagination)
        total = await self.collection.count_documents(query)

        # Ambil dokumen dengan skip & limit untuk pagination
        skip = (page - 1) * limit
        cursor = (
            self.collection.find(query)
            .sort("scraped_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        articles = await cursor.to_list(length=limit)

        return articles, total

    async def update_one(self, article_id: str, update_data: ArticleUpdate) -> bool:
        """
        Memperbarui dokumen artikel (partial update).
        Hanya field yang tidak None yang akan diupdate.

        Returns:
            bool: True jika update berhasil, False jika dokumen tidak ditemukan.
        """
        if not ObjectId.is_valid(article_id):
            return False

        # Hanya ambil field yang benar-benar diisi (bukan None)
        update_fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
        if not update_fields:
            return False

        result = await self.collection.update_one(
            {"_id": ObjectId(article_id)},
            {"$set": update_fields},
        )
        return result.modified_count > 0

    async def url_exists(self, url: str) -> bool:
        """
        Cek cepat apakah sebuah URL sudah ada di database.
        Lebih efisien daripada find_by_url karena hanya mengecek keberadaan.
        """
        count = await self.collection.count_documents({"url": url}, limit=1)
        return count > 0

    async def find_unsummarized(self, limit: int = 200) -> list[dict]:
        """
        Mengambil artikel yang belum memiliki ringkasan AI.
        Digunakan untuk proses re-summarize massal.

        Returns:
            list[dict]: Daftar dokumen artikel yang belum diringkas.
        """
        query = {
            "$or": [
                {"is_summarized": False},
                {"is_summarized": {"$exists": False}},
                {"summary": None},
                {"summary": {"$exists": False}},
            ]
        }
        cursor = self.collection.find(query).limit(limit)
        return await cursor.to_list(length=limit)

    async def delete_by_date(self, target_date: date, source: Optional[str] = None) -> int:
        """
        Menghapus semua artikel pada tanggal tertentu.
        Opsional: filter berdasarkan sumber portal.

        Returns:
            int: Jumlah artikel yang berhasil dihapus.
        """
        query: dict = {"published_date": str(target_date)}
        if source:
            query["source"] = source.lower()

        result = await self.collection.delete_many(query)
        return result.deleted_count
