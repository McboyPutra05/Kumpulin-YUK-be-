"""
deps.py
-------
FastAPI Dependency Injection — menyediakan instance service yang sudah dikonfigurasi
ke endpoint via parameter fungsi. Pola ini memudahkan testing (bisa di-mock).
"""

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.client import get_database
from app.db.repositories.article_repo import ArticleRepository
from app.services.article_service import ArticleService


def get_article_repo(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ArticleRepository:
    """Menyediakan instance ArticleRepository yang sudah terhubung ke database."""
    return ArticleRepository(db)


def get_article_service(
    repo: ArticleRepository = Depends(get_article_repo),
) -> ArticleService:
    """Menyediakan instance ArticleService yang sudah terhubung ke repository."""
    return ArticleService(repo)
