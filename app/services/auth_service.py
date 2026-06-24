import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError

from app.config import settings

# Setup untuk bcrypt (hash password)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """Service layer untuk logika Autentikasi (Hash, JWT, SMTP Email)."""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt

    @staticmethod
    def generate_verification_code() -> str:
        """Buat 6 digit kode acak untuk OTP."""
        return ''.join(random.choices(string.digits, k=6))

    @staticmethod
    def send_verification_email(to_email: str, code: str) -> bool:
        """Kirim email berisi OTP."""
        # Jika belum di-config SMTP di .env, kita kembalikan True dan print ke console saja (untuk dev)
        if not settings.smtp_email or not settings.smtp_password:
            print(f"[DEV MODE] Email verification code for {to_email}: {code}")
            return True

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Kode Verifikasi Kumpulin Artikel"
        msg["From"] = settings.smtp_email
        msg["To"] = to_email

        text = f"Halo,\n\nKode verifikasi Anda adalah: {code}\nKode ini berlaku selama 10 menit.\n\nTerima kasih."
        html = f"""
        <html>
          <body>
            <h2>Halo,</h2>
            <p>Terima kasih telah mendaftar. Kode verifikasi Anda adalah:</p>
            <h1 style="color: #4CAF50; font-size: 32px;">{code}</h1>
            <p>Kode ini berlaku selama 10 menit.</p>
            <p>Terima kasih,<br>Tim Kumpulin Artikel</p>
          </body>
        </html>
        """

        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        msg.attach(part1)
        msg.attach(part2)

        try:
            # Gunakan koneksi SMTP (default Gmail port 587)
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_email, settings.smtp_password)
            server.sendmail(settings.smtp_email, to_email, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[ERROR] Gagal mengirim email ke {to_email}: {e}")
            return False
