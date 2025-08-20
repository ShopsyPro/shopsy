"""
Core email service module.

This module provides a unified EmailService class that combines all email
functionality including SES client, PDF generation, templates, and logging.
"""

import logging
from .config import email_config
from .client import ses_client
from .pdf_generator import pdf_generator
from .templates import email_templates
from .logger import email_logger

module_logger = logging.getLogger(__name__)


class EmailService:
    """
    Unified email service that combines all email functionality.
    
    This service provides methods for sending various types of emails including
    basic emails, emails with attachments, delivery notifications, invoices,
    and OTP verification emails.
    """
    
    def __init__(self):
        """Initialize the email service with all components."""
        self.config = email_config
        self.client = ses_client
        self.pdf_generator = pdf_generator
        self.templates = email_templates
        self.logger = email_logger
    
    def send_email(self, to_email, subject, html_content, text_content=None):
        """
        Send a basic email using AWS SES.
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_content (str): HTML content of the email
            text_content (str, optional): Plain text content (fallback)
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        success = self.client.send_email(to_email, subject, html_content, text_content)
        
        # Log the email activity
        self.logger.log_email_activity(
            to_email=to_email,
            subject=subject,
            success=success
        )
        
        return success
    
    def send_email_with_attachment(self, to_email, subject, html_content, text_content=None, 
                                 attachment_data=None, attachment_name=None):
        """
        Send an email with attachment using AWS SES.
        
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
        success = self.client.send_email_with_attachment(
            to_email, subject, html_content, text_content, 
            attachment_data, attachment_name
        )
        
        # Log the email activity
        self.logger.log_email_activity(
            to_email=to_email,
            subject=subject,
            success=success,
            email_type='attachment'
        )
        
        return success
    
    def generate_invoice_pdf(self, order_data, shop_name):
        """
        Generate a PDF invoice for an order.
        
        Args:
            order_data (dict): Order data containing order details
            shop_name (str): Name of the shop
            
        Returns:
            bytes: PDF content as bytes
        """
        return self.pdf_generator.generate_invoice_pdf(order_data, shop_name)
    
    def send_order_delivery_email(self, to_email, order_id, shop_name, stock_items=None, 
                                stock_item=None, product_name=None):
        """
        Send order delivery notification email.
        
        Args:
            to_email (str): Recipient email address
            order_id (str): Order ID
            shop_name (str): Name of the shop
            stock_items (list, optional): List of stock items with product names
            stock_item (str, optional): Single stock item (legacy support)
            product_name (str, optional): Single product name (legacy support)
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        module_logger.info(f"[EMAIL] Sending delivery email for order {order_id} to {to_email}")
        
        # Handle legacy format for backward compatibility
        if stock_items is None and stock_item is not None and product_name is not None:
            stock_items = [{
                'stock_item': stock_item,
                'product_name': product_name
            }]
        
        # Ensure we have stock items to send
        if not stock_items:
            module_logger.warning(f"[EMAIL] No stock items provided for delivery email {order_id}")
            return False
        
        # Generate email content using templates
        subject, html_content = self.templates.get_delivery_email_content(
            order_id, shop_name, stock_items
        )
        
        if not html_content:
            module_logger.error(f"[EMAIL] Failed to generate delivery email content for {order_id}")
            return False
        
        # Send the email
        success = self.client.send_email(to_email, subject, html_content)
        
        # Log the delivery email activity
        self.logger.log_delivery_email(
            to_email=to_email,
            order_id=order_id,
            success=success,
            items_count=len(stock_items)
        )
        
        module_logger.info(f"[EMAIL] Delivery email result for {order_id}: {success}")
        return success
    
    def send_invoice_email(self, to_email, order_id, shop_name, order_data):
        """
        Send invoice email with PDF attachment.
        
        Args:
            to_email (str): Recipient email address
            order_id (str): Order ID
            shop_name (str): Name of the shop
            order_data (dict): Order data for PDF generation
        
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        module_logger.info(f"[EMAIL] Sending invoice email for order {order_id} to {to_email}")
        
        try:
            # Generate PDF invoice
            pdf_content = self.generate_invoice_pdf(order_data, shop_name)
            if not pdf_content:
                module_logger.error(f"[EMAIL] Failed to generate PDF for invoice {order_id}")
                return False
            
            # Generate email content using templates with order data
            subject, html_content = self.templates.get_invoice_email_content(order_id, shop_name, order_data)
            
            # Send email with PDF attachment
            success = self.send_email_with_attachment(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                attachment_data=pdf_content,
                attachment_name=f"invoice_{order_id}.pdf"
            )
            
            # Log the invoice email activity
            self.logger.log_invoice_email(
                to_email=to_email,
                order_id=order_id,
                success=success
            )
            
            module_logger.info(f"[EMAIL] Invoice email result for {order_id}: {success}")
            return success
            
        except Exception as e:
            module_logger.error(f"[EMAIL] Failed to send invoice email for {order_id}: {str(e)}")
            return False
    
    def send_customer_otp_email(self, to_email, otp_code):
        """
        Send OTP verification email to customer.
        
        Args:
            to_email (str): Customer email address
            otp_code (str): 6-digit OTP code
        
        Returns:
            bool: True if email was sent successfully
        """
        module_logger.info(f"[EMAIL] Sending OTP email to {to_email}")
        
        try:
            # Generate OTP email content using templates
            subject, html_content = self.templates.get_otp_email_content(otp_code)
            
            # Send the email
            success = self.client.send_email(to_email, subject, html_content)
            
            # Log the OTP email activity
            self.logger.log_otp_email(
                to_email=to_email,
                success=success
            )
            
            module_logger.info(f"[EMAIL] OTP email result for {to_email}: {success}")
            return success
            
        except Exception as e:
            module_logger.error(f"[EMAIL] Failed to send OTP email to {to_email}: {str(e)}")
            return False
    
    def log_email_activity(self, to_email, subject, success, order_id=None):
        """
        Log email activity (backward compatibility method).
        
        Args:
            to_email (str): Recipient email
            subject (str): Email subject
            success (bool): Whether email was sent successfully
            order_id (str, optional): Order ID if applicable
        """
        self.logger.log_email_activity(to_email, subject, success, order_id)
    
    def is_configured(self):
        """Check if the email service is properly configured."""
        return self.config.is_configured() and self.client.is_ready()


# Create a global instance
email_service = EmailService()

# Export main classes and instances
__all__ = [
    'EmailService',
    'email_service',
    'email_config',
    'ses_client', 
    'pdf_generator',
    'email_templates',
    'email_logger'
] 