from datetime import datetime, timezone
from app.models.pdf_job import db
from sqlalchemy import CheckConstraint
import uuid
import bcrypt


class User(db.Model):
    __tablename__ = "users"

    # Primary Key
    id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # User Credentials
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # Metadata
    meta_data = db.Column(
        db.Text, nullable=True
    )  # JSON string for service info, configuration, etc.

    # Webhook Configuration
    webhook_secret = db.Column(db.String(64), nullable=True)
    webhook_secret_created_at = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "length(username) >= 3 AND length(username) <= 50",
            name="check_username_length",
        ),
        CheckConstraint(
            "length(password_hash) <= 255", name="check_password_hash_length"
        ),
        CheckConstraint(
            "length(meta_data) <= 5120", name="check_user_meta_data_length"
        ),
        CheckConstraint(
            "webhook_secret IS NULL OR length(webhook_secret) <= 64",
            name="check_webhook_secret_length",
        ),
        db.Index("idx_username", "username"),
    )

    def set_password(self, password: str):
        """Hash and set the password"""
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify the password"""
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    def __repr__(self):
        return f"<User {self.username}>"
