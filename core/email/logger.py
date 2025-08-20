"""
Email activity logging module.

This module handles logging of email activities including sends,
failures, and other email-related events for audit and debugging purposes.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailLogger:
    """Email activity logging utilities."""
    
    def __init__(self, log_file_path='logs/email_log.txt'):
        """
        Initialize email logger.
        
        Args:
            log_file_path (str): Path to the email log file
        """
        self.log_file_path = log_file_path
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """Ensure the log directory exists."""
        log_dir = os.path.dirname(self.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                logger.info(f"Created log directory: {log_dir}")
            except Exception as e:
                logger.error(f"Failed to create log directory: {e}")
    
    def log_email_activity(self, to_email, subject, success, order_id=None, email_type=None):
        """
        Log email activity to a file.
        
        Args:
            to_email (str): Recipient email
            subject (str): Email subject
            success (bool): Whether email was sent successfully
            order_id (str, optional): Order ID if applicable
            email_type (str, optional): Type of email (invoice, delivery, otp, etc.)
        """
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'to_email': to_email,
                'subject': subject,
                'success': success,
                'order_id': order_id,
                'email_type': email_type or 'unknown'
            }
            
            # Create formatted log entry
            log_line = (
                f"[{log_entry['timestamp']}] "
                f"{'SUCCESS' if success else 'FAILED'} | "
                f"To: {to_email} | "
                f"Subject: {subject} | "
                f"Type: {log_entry['email_type']}"
            )
            
            if order_id:
                log_line += f" | Order: {order_id}"
            
            # Append to email log file
            with open(self.log_file_path, 'a', encoding='utf-8') as log_file:
                log_file.write(f"{log_line}\n")
            
            logger.debug(f"Email activity logged: {log_line}")
                
        except Exception as e:
            logger.error(f"Failed to log email activity: {str(e)}")
    
    def log_delivery_email(self, to_email, order_id, success, items_count=None):
        """
        Log delivery email activity.
        
        Args:
            to_email (str): Recipient email
            order_id (str): Order ID
            success (bool): Whether email was sent successfully
            items_count (int, optional): Number of items delivered
        """
        subject = f"Order Delivery Notification - Order #{order_id}"
        if items_count:
            subject += f" ({items_count} items)"
        
        self.log_email_activity(
            to_email=to_email,
            subject=subject,
            success=success,
            order_id=order_id,
            email_type='delivery'
        )
    
    def log_invoice_email(self, to_email, order_id, success):
        """
        Log invoice email activity.
        
        Args:
            to_email (str): Recipient email
            order_id (str): Order ID
            success (bool): Whether email was sent successfully
        """
        subject = f"Invoice for Order #{order_id}"
        
        self.log_email_activity(
            to_email=to_email,
            subject=subject,
            success=success,
            order_id=order_id,
            email_type='invoice'
        )
    
    def log_otp_email(self, to_email, success):
        """
        Log OTP email activity.
        
        Args:
            to_email (str): Recipient email
            success (bool): Whether email was sent successfully
        """
        subject = "OTP Verification Email"
        
        self.log_email_activity(
            to_email=to_email,
            subject=subject,
            success=success,
            order_id=None,
            email_type='otp'
        )
    
    def get_recent_logs(self, count=100):
        """
        Get recent email log entries.
        
        Args:
            count (int): Number of recent entries to return
            
        Returns:
            list: List of recent log entries
        """
        try:
            if not os.path.exists(self.log_file_path):
                return []
            
            with open(self.log_file_path, 'r', encoding='utf-8') as log_file:
                lines = log_file.readlines()
                return [line.strip() for line in lines[-count:] if line.strip()]
        
        except Exception as e:
            logger.error(f"Failed to read email logs: {str(e)}")
            return []
    
    def get_logs_for_order(self, order_id):
        """
        Get all log entries for a specific order.
        
        Args:
            order_id (str): Order ID to search for
            
        Returns:
            list: List of log entries for the order
        """
        try:
            if not os.path.exists(self.log_file_path):
                return []
            
            order_logs = []
            with open(self.log_file_path, 'r', encoding='utf-8') as log_file:
                for line in log_file:
                    if f"Order: {order_id}" in line:
                        order_logs.append(line.strip())
            
            return order_logs
        
        except Exception as e:
            logger.error(f"Failed to read email logs for order {order_id}: {str(e)}")
            return []


# Global email logger instance
email_logger = EmailLogger() 