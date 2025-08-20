"""
Email service configuration module.

This module handles AWS SES configuration and environment variables
for the email service functionality.
"""

import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class EmailConfig:
    """Configuration class for email service settings."""
    
    def __init__(self):
        """Initialize email configuration from environment variables."""
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '')
        self.aws_region = os.getenv('AWS_REGION', 'eu-north-1')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@shopsy.pro')
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate that required configuration is present."""
        if not all([self.aws_access_key, self.aws_secret_key]):
            logger.warning("AWS credentials not configured properly")
            return False
        return True
    
    def is_configured(self):
        """Check if email service is properly configured."""
        return bool(self.aws_access_key and self.aws_secret_key)
    
    def get_ses_config(self):
        """Get SES client configuration dictionary."""
        return {
            'aws_access_key_id': self.aws_access_key,
            'aws_secret_access_key': self.aws_secret_key,
            'region_name': self.aws_region
        }


# Global configuration instance
email_config = EmailConfig() 