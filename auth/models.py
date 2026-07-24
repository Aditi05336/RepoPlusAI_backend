"""
models.py

SQLAlchemy ORM models for RepoPulse AI Authentication.
Contains the User data model and bcrypt password hashing utilities.
"""

from datetime import datetime, timezone
import bcrypt
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    github_username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def set_password(self, password: str) -> None:
        """Hash plain text password using bcrypt and store in password_hash."""
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        self.password_hash = hashed.decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify plain text password against stored bcrypt hash."""
        if not self.password_hash:
            return False
        password_bytes = password.encode("utf-8")
        hash_bytes = self.password_hash.encode("utf-8")
        try:
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Serialize user object without sensitive data (no password_hash)."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "github_username": self.github_username,
            "username": self.github_username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
