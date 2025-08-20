"""
S3 Storage Configuration
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AWS S3 Configuration
ACCESS_KEY = os.getenv('ACCESS_KEY')
SECRET_KEY = os.getenv('SECRET_ACCESS_KEY')
AWS_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
S3_URL_PREFIX = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/"

# File upload constraints
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB in bytes 