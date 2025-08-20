"""
Storage module for handling file operations and cloud storage.
"""

from .s3_client import s3_client, upload_file_to_s3, delete_file_from_s3
from .config import S3_URL_PREFIX, AWS_BUCKET_NAME, AWS_REGION

__all__ = [
    's3_client',
    'upload_file_to_s3', 
    'delete_file_from_s3',
    'S3_URL_PREFIX',
    'AWS_BUCKET_NAME', 
    'AWS_REGION'
] 