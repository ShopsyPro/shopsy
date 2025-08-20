import os
from typing import Optional

class CloudflareConfig:
    """Configuration for Cloudflare Turnstile"""
    
    @staticmethod
    def get_site_key() -> Optional[str]:
        """Get Cloudflare site key from environment"""
        return os.getenv('C_SITE_KEY')
    
    @staticmethod
    def get_secret_key() -> Optional[str]:
        """Get Cloudflare secret key from environment"""
        return os.getenv('C_SECRET_KEY')
    
    @staticmethod
    def is_configured() -> bool:
        """Check if Cloudflare is properly configured"""
        return bool(CloudflareConfig.get_site_key() and CloudflareConfig.get_secret_key())
    
    @staticmethod
    def get_verify_url() -> str:
        """Get Cloudflare verification URL"""
        return "https://challenges.cloudflare.com/turnstile/v0/siteverify"
