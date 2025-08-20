"""
AWS SES client module.

This module handles the AWS SES client initialization and provides
basic email sending functionality using the SES API.
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
from .config import email_config

logger = logging.getLogger(__name__)


class SESClient:
    """AWS SES client wrapper for email sending functionality."""
    
    def __init__(self):
        """Initialize the SES client."""
        self.ses_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the AWS SES client."""
        if not email_config.is_configured():
            logger.error("Email configuration not properly set up")
            return
        
        try:
            self.ses_client = boto3.client('ses', **email_config.get_ses_config())
            logger.info(f"SES client initialized for region: {email_config.aws_region}")
        except Exception as e:
            logger.error(f"Failed to initialize SES client: {e}")
            self.ses_client = None
    
    def is_ready(self):
        """Check if the SES client is ready to send emails."""
        return self.ses_client is not None
    
    def send_email(self, to_email, subject, html_content, text_content=None):
        """
        Send an email using AWS SES API.
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_content (str): HTML content of the email
            text_content (str, optional): Plain text content (fallback)
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        logger.info(f"[EMAIL] send_email called for {to_email}")
        logger.info(f"[EMAIL] AWS Config check - Access Key: {'SET' if email_config.aws_access_key else 'NOT SET'}, Secret Key: {'SET' if email_config.aws_secret_key else 'NOT SET'}")
        
        if not self.is_ready():
            logger.error(f"[EMAIL] SES client not initialized")
            return False
        
        try:
            # Prepare the message body
            body = {}
            
            if text_content:
                body['Text'] = {'Data': text_content, 'Charset': 'UTF-8'}
            
            if html_content:
                body['Html'] = {'Data': html_content, 'Charset': 'UTF-8'}
            
            # Send email using SES API
            logger.info(f"[EMAIL] Sending email via SES API to {to_email}")
            if self.ses_client is None:
                raise Exception("SES client is None")
            response = self.ses_client.send_email(
                Source=email_config.from_email,
                Destination={'ToAddresses': [to_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': body
                }
            )
            
            message_id = response['MessageId']
            logger.info(f"[EMAIL] Email sent successfully to {to_email}, MessageId: {message_id}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"[EMAIL] AWS SES ClientError for {to_email}: {error_code} - {error_message}")
            return False
        except NoCredentialsError:
            logger.error(f"[EMAIL] AWS credentials not found for {to_email}")
            return False
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    def send_email_with_attachment(self, to_email, subject, html_content, text_content=None, 
                                 attachment_data=None, attachment_name=None):
        """
        Send an email with attachment using AWS SES API.
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_content (str): HTML content of the email
            text_content (str, optional): Plain text content (fallback)
            attachment_data (bytes, optional): PDF attachment data
            attachment_name (str, optional): Name of the attachment file
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        logger.info(f"[EMAIL] send_email_with_attachment called for {to_email}")
        
        if not self.is_ready():
            logger.error(f"[EMAIL] SES client not initialized")
            return False
        
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.application import MIMEApplication
            
            # Create message container
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = email_config.from_email
            msg['To'] = to_email
            
            # Add text content
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Add HTML content
            if html_content:
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Add attachment if provided
            if attachment_data and attachment_name:
                attachment = MIMEApplication(attachment_data)
                attachment.add_header('Content-Disposition', 'attachment', filename=attachment_name)
                msg.attach(attachment)
            
            # Send email using SES API
            logger.info(f"[EMAIL] Sending email with attachment via SES API to {to_email}")
            if self.ses_client is None:
                raise Exception("SES client is None")
            response = self.ses_client.send_raw_email(
                Source=email_config.from_email,
                Destinations=[to_email],
                RawMessage={'Data': msg.as_string()}
            )
            
            message_id = response['MessageId']
            logger.info(f"[EMAIL] Email with attachment sent successfully to {to_email}, MessageId: {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send email with attachment to {to_email}: {str(e)}", exc_info=True)
            return False


# Global SES client instance
ses_client = SESClient() 