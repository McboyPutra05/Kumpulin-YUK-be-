from datetime import datetime
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.models.user import UserCreate, UserInDB

class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["users"]

    async def get_by_email(self, email: str) -> Optional[dict]:
        """Ambil user berdasarkan email (case-insensitive)."""
        return await self.collection.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}})

    async def get_by_id(self, user_id: str) -> Optional[dict]:
        """Ambil user berdasarkan ID."""
        try:
            return await self.collection.find_one({"_id": ObjectId(user_id)})
        except:
            return None

    async def create(self, user_in: UserCreate, hashed_password: str, verification_code: str, code_expires_at: datetime) -> str:
        """Simpan user baru dengan status belum terverifikasi."""
        user_doc = {
            "name": user_in.name,
            "email": user_in.email.lower(),
            "hashed_password": hashed_password,
            "is_verified": False,
            "verification_code": verification_code,
            "verification_code_expires_at": code_expires_at,
            "created_at": datetime.utcnow()
        }
        result = await self.collection.insert_one(user_doc)
        return str(result.inserted_id)

    async def mark_verified(self, user_id: str) -> bool:
        """Tandai user sudah terverifikasi dan hapus kode OTP."""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_verified": True}, "$unset": {"verification_code": "", "verification_code_expires_at": ""}}
        )
        return result.modified_count > 0

    async def update_verification_code(self, user_id: str, new_code: str, code_expires_at: datetime) -> bool:
        """Update kode OTP baru jika user minta resend."""
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"verification_code": new_code, "verification_code_expires_at": code_expires_at}}
        )
        return result.modified_count > 0

    async def setup_indexes(self):
        """Buat index unique untuk email."""
        await self.collection.create_index("email", unique=True)
        print("[OK] MongoDB indexes created for 'users' collection.")
