from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt

from app.config import settings
from app.db.client import get_database
from app.db.repositories.user_repo import UserRepository
from app.models.user import UserCreate, UserLogin, UserResponse, Token, VerifyCodeRequest, ResendCodeRequest
from app.services.auth_service import AuthService

router = APIRouter()

def get_user_repo(db=Depends(get_database)) -> UserRepository:
    return UserRepository(db)

# Dependency untuk mendapatkan user yang sedang login dari token
async def get_current_user(token: str = Depends(lambda req: req.headers.get("Authorization")), user_repo: UserRepository = Depends(get_user_repo)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token or not token.startswith("Bearer "):
        raise credentials_exception
    
    token = token.split(" ")[1]
    
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await user_repo.get_by_email(email)
    if user is None:
        raise credentials_exception
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, user_repo: UserRepository = Depends(get_user_repo)):
    """Register user baru dan kirim kode verifikasi ke email."""
    # Cek apakah email sudah terdaftar
    existing_user = await user_repo.get_by_email(user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sudah terdaftar"
        )

    # Hash password
    hashed_password = AuthService.get_password_hash(user_in.password)
    
    # Generate verification code
    code = AuthService.generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Simpan ke database
    await user_repo.create(user_in, hashed_password, code, expires_at)

    # Kirim email
    email_sent = AuthService.send_verification_email(user_in.email, code)
    if not email_sent:
        # Kita tidak gagalkan register, tapi beritahu user bahwa email gagal dan butuh resend
        print(f"[WARNING] Gagal mengirim email ke {user_in.email}")

    return {"message": "Registrasi berhasil. Silakan cek email Anda untuk kode verifikasi."}


@router.post("/verify")
async def verify_email(req: VerifyCodeRequest, user_repo: UserRepository = Depends(get_user_repo)):
    """Verifikasi email menggunakan kode OTP yang dikirim."""
    user = await user_repo.get_by_email(req.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User tidak ditemukan")
    
    if user.get("is_verified"):
        return {"message": "Email sudah terverifikasi sebelumnya."}

    # Cek apakah kode valid dan belum expired
    if user.get("verification_code") != req.code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kode verifikasi salah")
    
    if user.get("verification_code_expires_at") and user.get("verification_code_expires_at") < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kode verifikasi sudah kadaluarsa")

    # Update status ke verified
    await user_repo.mark_verified(str(user["_id"]))
    
    return {"message": "Email berhasil diverifikasi. Silakan login."}


@router.post("/resend-code")
async def resend_verification_code(req: ResendCodeRequest, user_repo: UserRepository = Depends(get_user_repo)):
    """Kirim ulang kode verifikasi ke email."""
    user = await user_repo.get_by_email(req.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User tidak ditemukan")
    
    if user.get("is_verified"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email sudah terverifikasi")

    new_code = AuthService.generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    await user_repo.update_verification_code(str(user["_id"]), new_code, expires_at)
    AuthService.send_verification_email(req.email, new_code)

    return {"message": "Kode verifikasi baru telah dikirim ke email Anda."}


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, user_repo: UserRepository = Depends(get_user_repo)):
    """Login untuk mendapatkan JWT Access Token."""
    user = await user_repo.get_by_email(user_in.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau password salah")

    if not AuthService.verify_password(user_in.password, user.get("hashed_password")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email atau password salah")

    if not user.get("is_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Akun belum diverifikasi. Silakan cek email Anda.")

    # Generate token
    access_token = AuthService.create_access_token(data={"sub": user["email"]})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            is_verified=user["is_verified"],
            created_at=user["created_at"]
        )
    )

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Ambil data profil user yang sedang login."""
    return UserResponse(
        id=str(current_user["_id"]),
        name=current_user["name"],
        email=current_user["email"],
        is_verified=current_user["is_verified"],
        created_at=current_user["created_at"]
    )
