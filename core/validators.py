"""
Validation utilities for the application
"""

import os
from .storage.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_image_file(file):
    """
    Comprehensive image file validation
    
    Args:
        file: Flask file object from request.files
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not file:
        return False, "No file provided"
        
    if not file.filename:
        return False, "Empty filename"
        
    # Check file extension
    if not allowed_file(file.filename):
        return False, f"File type not supported. Only {', '.join(ALLOWED_EXTENSIONS).upper()} files are allowed"
        
    # Get file size by seeking to end and getting position
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    # Check file size (2MB limit)
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        return False, f"File size ({size_mb:.1f}MB) exceeds maximum allowed size of 2MB"
    
    # Check if file is actually an image by reading first few bytes
    file.seek(0)
    header = file.read(10)
    file.seek(0)  # Reset to beginning
    
    # Common image file signatures
    image_signatures = {
        b'\xff\xd8\xff': 'JPEG',
        b'\x89PNG\r\n\x1a\n': 'PNG',
        b'GIF87a': 'GIF',
        b'GIF89a': 'GIF',
        b'WEBP': 'WEBP'
    }
    
    is_valid_image = False
    for signature in image_signatures:
        if header.startswith(signature):
            is_valid_image = True
            break
    
    if not is_valid_image:
        return False, "File is not a valid image format"
    
    # Check for banned image ID
    banned_image_id = "bda5b4158afc4fb3b01dd6c34f67726b"
    if banned_image_id in file.filename:
        return False, "This image cannot be used. Please select a different image"
    
    return True, "Valid image file"

 