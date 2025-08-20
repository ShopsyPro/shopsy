import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration class containing all Flask app settings"""
    
    # Secret key configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "default-shop-express-secret-key-change-in-production")
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_PERMANENT = True
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Remember cookie configuration
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True
    
    # Static folder configuration
    STATIC_FOLDER = 'static'
    
    # Cloudflare Turnstile configuration
    CLOUDFLARE_SITE_KEY = os.getenv("C_SITE_KEY")
    CLOUDFLARE_SECRET_KEY = os.getenv("C_SECRET_KEY")

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 