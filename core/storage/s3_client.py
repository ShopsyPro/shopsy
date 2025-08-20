"""
S3 Client and file operations
"""

import os
import boto3
import uuid
from botocore.exceptions import NoCredentialsError, ClientError
from werkzeug.utils import secure_filename

from .config import ACCESS_KEY, SECRET_KEY, AWS_BUCKET_NAME, AWS_REGION, S3_URL_PREFIX
from ..validators import validate_image_file

# Initialize S3 client
try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=AWS_REGION
    )
except Exception as e:
    print(f"Error initializing S3 client: {e}")
    s3_client = None


def upload_file_to_s3(file, folder="products"):
    """
    Upload a file to S3 bucket with comprehensive validation
    
    Args:
        file: Flask file object from request.files
        folder: Optional folder path within bucket (default: "products")
        
    Returns:
        tuple: (success, result) where result is URL on success or error message on failure
    """
    if not s3_client:
        error_msg = "S3 client not initialized - check AWS credentials in .env file"
        print(error_msg)
        print(f"ACCESS_KEY: {'Set' if ACCESS_KEY else 'Not set'}")
        print(f"SECRET_ACCESS_KEY: {'Set' if SECRET_KEY else 'Not set'}")
        print(f"BUCKET_NAME: {AWS_BUCKET_NAME}")
        print(f"REGION: {AWS_REGION}")
        return False, error_msg
    
    # Validate the image file
    is_valid, validation_message = validate_image_file(file)
    if not is_valid:
        print(f"File validation failed: {validation_message}")
        return False, validation_message
        
    # Create a unique filename to prevent overwriting
    original_filename = secure_filename(file.filename)
    extension = original_filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{folder}/{uuid.uuid4().hex}.{extension}"
    
    try:
        print(f"Attempting to upload {original_filename} to S3 bucket {AWS_BUCKET_NAME}")
        print(f"Content type: {file.content_type}")
        
        # Get file size for logging
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        print(f"File size: {file_size} bytes ({file_size / (1024 * 1024):.2f}MB)")
        
        # Upload the file
        s3_client.upload_fileobj(
            file, 
            AWS_BUCKET_NAME, 
            unique_filename,
            ExtraArgs={
                'ContentType': file.content_type
            }
        )
        
        # Return the public URL
        url = f"{S3_URL_PREFIX}{unique_filename}"
        print(f"Successfully uploaded to S3: {url}")
        return True, url
        
    except NoCredentialsError as e:
        error_msg = f"AWS credentials not found: {str(e)}"
        print(error_msg)
        print("Make sure ACCESS_KEY and SECRET_ACCESS_KEY are set in .env file")
        return False, "Upload failed: Invalid AWS credentials"
        
    except ClientError as e:
        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '')
        print(f"AWS S3 error: {e}")
        print(f"Error code: {error_code}")
        
        if "AccessDenied" in str(e):
            error_msg = "Upload failed: Access denied to S3 bucket"
            print("Access denied - check IAM permissions for your AWS credentials")
        elif "NoSuchBucket" in str(e):
            error_msg = f"Upload failed: S3 bucket '{AWS_BUCKET_NAME}' not found"
            print(f"Bucket {AWS_BUCKET_NAME} does not exist or you don't have access to it")
        elif "EntityTooLarge" in str(e):
            error_msg = "Upload failed: File size too large"
        else:
            error_msg = f"Upload failed: AWS S3 error ({error_code})"
            
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        print(f"Error uploading file: {e}")
        import traceback
        traceback.print_exc()
        return False, error_msg


def delete_file_from_s3(file_url):
    """
    Delete a file from S3 bucket
    
    Args:
        file_url: Full URL of the file to delete
        
    Returns:
        True if deletion successful, False otherwise
    """
    if not s3_client:
        print("S3 client not initialized - check AWS credentials in .env file")
        return False
        
    if not file_url:
        print("No file URL provided for deletion")
        return False
        
    if not file_url.startswith(S3_URL_PREFIX):
        print(f"URL '{file_url}' does not match expected S3 URL prefix '{S3_URL_PREFIX}'")
        return False
        
    # Extract the object key from the URL
    object_key = file_url.replace(S3_URL_PREFIX, '')
    print(f"Attempting to delete S3 object: {object_key}")
    
    try:
        # Delete the file
        response = s3_client.delete_object(
            Bucket=AWS_BUCKET_NAME,
            Key=object_key
        )
        print(f"S3 delete response: {response}")
        print(f"Successfully deleted object {object_key} from bucket {AWS_BUCKET_NAME}")
        return True
    except NoCredentialsError as e:
        print(f"AWS credentials not found: {str(e)}")
        print("Make sure ACCESS_KEY and SECRET_ACCESS_KEY are set in .env file")
    except ClientError as e:
        print(f"AWS S3 error: {e}")
        if "AccessDenied" in str(e):
            print("Access denied - check IAM permissions for your AWS credentials")
        elif "NoSuchKey" in str(e):
            print(f"Object {object_key} not found in bucket {AWS_BUCKET_NAME}")
    except Exception as e:
        print(f"Error deleting file: {e}")
        import traceback
        traceback.print_exc()
        
    return False 