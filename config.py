"""Configuration for the temperature monitoring demo."""
import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "demo-only-change-this-secret-key")
    # SQLite makes the demo runnable immediately. Set DATABASE_URL to a MySQL
    # SQLAlchemy URL to use MySQL without changing application code.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///temperature_monitor.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    ESCALATION_MINUTES = int(os.environ.get("ESCALATION_MINUTES", "5"))
    PROLONGED_MINUTES = int(os.environ.get("PROLONGED_MINUTES", "5"))
