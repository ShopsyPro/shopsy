"""
Email templates module.

This module handles specialized email templates including delivery notifications,
OTP verification, and invoice emails with proper HTML formatting and styling.
"""

import os
import logging
from datetime import datetime
from flask import render_template_string
from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


class EmailTemplates:
    """Email template generation and formatting utilities."""
    
    def __init__(self):
        """Initialize email templates."""
        self.templates_dir = 'templates/email'
    
    def get_otp_email_content(self, otp_code):
        """
        Generate OTP verification email content.
        
        Args:
            otp_code (str): 6-digit OTP code
            
        Returns:
            tuple: (subject, html_content)
        """
        subject = "🔐 Verify Your Email - Order Tracking | ShopsyPro"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Verification</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .email-container {{
                    background-color: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .shopsy-logo {{
                    font-size: 28px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .content {{
                    padding: 40px 30px;
                    text-align: center;
                }}
                .otp-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    font-size: 32px;
                    font-weight: bold;
                    letter-spacing: 8px;
                    padding: 20px;
                    border-radius: 10px;
                    margin: 30px 0;
                    text-align: center;
                    font-family: 'Courier New', monospace;
                }}
                .instruction {{
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 20px;
                    margin: 20px 0;
                    border-radius: 0 5px 5px 0;
                }}
                .warning {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }}
                .logo {{
                    font-size: 24px;
                    margin-bottom: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="shopsy-logo">ShopsyPro</div>
                    <p>Email Verification Required</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #333; margin-bottom: 20px;">Verify Your Email Address</h2>
                    
                    <p>We received a request to access your order tracking information. To proceed, please enter the verification code below:</p>
                    
                    <div class="otp-box">
                        {otp_code}
                    </div>
                    
                    <div class="instruction">
                        <h3 style="margin-top: 0; color: #667eea;">How to use this code:</h3>
                        <ol style="text-align: left; margin: 10px 0;">
                            <li>Go back to the order tracking page</li>
                            <li>Enter the 6-digit code above</li>
                            <li>Click "Verify" to access your orders</li>
                        </ol>
                    </div>
                    
                    <div class="warning">
                        <strong>⚠️ Security Note:</strong> This code expires in 10 minutes and can only be used once. If you didn't request this verification, you can safely ignore this email.
                    </div>
                    
                    <p style="margin-top: 30px;">If you're having trouble, please contact our support team.</p>
                </div>
                
                <div class="footer">
                    <div class="logo">ShopsyPro</div>
                    <p>This is an automated email from ShopsyPro platform.<br>Please do not reply to this email.</p>
                    <p style="margin-top: 15px;">
                        <a href="#" style="color: #667eea; text-decoration: none;">Privacy Policy</a> | 
                        <a href="#" style="color: #667eea; text-decoration: none;">Support</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def get_delivery_email_content(self, order_id, shop_name, stock_items):
        """
        Generate delivery notification email content.
        
        Args:
            order_id (str): Order ID
            shop_name (str): Shop name
            stock_items (list): List of stock items with product names
            
        Returns:
            tuple: (subject, html_content)
        """
        subject = f"🎉 Order Delivered - {shop_name} | ShopsyPro"
        
        # Handle stock items formatting
        if not stock_items:
            return subject, ""
        
        # Create stock items HTML
        if len(stock_items) == 1:
            stock_html = f'<div class="stock-item">{stock_items[0]["stock_item"]}</div>'
            product_display = stock_items[0]["product_name"]
        else:
            stock_html = ""
            product_names = []
            for item in stock_items:
                stock_html += f'''
                <div class="stock-item" style="margin-bottom: 12px;">
                    <div style="font-size: 14px; color: #6b7280; margin-bottom: 4px;">
                        <strong>{item["product_name"]}</strong>
                    </div>
                    {item["stock_item"]}
                </div>
                '''
                product_names.append(item["product_name"])
            
            # Create product display string
            if len(set(product_names)) == 1:
                product_display = f'{product_names[0]} (x{len(stock_items)})'
            else:
                product_display = f'{len(stock_items)} Digital Products'
        
        # Try to use template file first, fallback to inline HTML
        try:
            template_path = os.path.join(self.templates_dir, 'order_delivery.html')
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    template_content = f.read()
                
                # Replace template variables
                html_content = template_content.replace('{{ shop_name }}', shop_name)
                html_content = html_content.replace('{{ order_id }}', order_id)
                html_content = html_content.replace('{{ stock_item }}', stock_html)
                html_content = html_content.replace('{{ product_name }}', product_display)
                html_content = html_content.replace('{{ delivery_date }}', 
                    datetime.now().strftime('%B %d, %Y at %I:%M %p UTC'))
                
                return subject, html_content
        
        except Exception as e:
            logger.warning(f"Could not load delivery template: {e}, using fallback")
        
        # Fallback inline HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Order Delivery</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #2563eb;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f8fafc;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
                .order-details {{
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #2563eb;
                }}
                .stock-item {{
                    background-color: #f1f5f9;
                    padding: 15px;
                    border-radius: 6px;
                    margin: 10px 0;
                    font-family: monospace;
                    word-break: break-all;
                    border: 1px solid #e2e8f0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    color: #6b7280;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎉 Order Delivered!</h1>
                <p>{shop_name}</p>
            </div>
            
            <div class="content">
                <p>Great news! Your order has been delivered and is ready to use.</p>
                
                <div class="order-details">
                    <h3>Order Information</h3>
                    <p><strong>Order ID:</strong> {order_id}</p>
                    <p><strong>Product:</strong> {product_display}</p>
                    <p><strong>Delivered:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}</p>
                </div>
                
                <div class="order-details">
                    <h3>Your Digital Products</h3>
                    {stock_html}
                </div>
                
                <p><strong>Important:</strong> Please save this information securely. This email contains your purchased digital content.</p>
            </div>
            
            <div class="footer">
                <p>Thank you for your purchase!</p>
                <p>ShopsyPro Platform</p>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def get_invoice_email_content(self, order_id, shop_name, order_data=None):
        """
        Generate invoice email content.
        
        Args:
            order_id (str): Order ID
            shop_name (str): Shop name
            order_data (dict, optional): Complete order data for template rendering
            
        Returns:
            tuple: (subject, html_content)
        """
        subject = f"📄 Invoice for Order #{order_id} - {shop_name}"
        
        # Try to use template file first with proper Jinja2 rendering
        try:
            template_path = os.path.join(self.templates_dir, 'invoice.html')
            if os.path.exists(template_path) and order_data:
                # Set up Jinja2 environment
                env = Environment(loader=FileSystemLoader('templates'))
                template = env.get_template('email/invoice.html')
                
                # Extract order data for template
                order_items = order_data.get('items', [])
                order_total = order_data.get('original_total', order_data.get('total_amount', 0))
                final_amount = order_data.get('total_amount', 0)
                discount_amount = order_data.get('discount_total', 0)
                sent_stock = order_data.get('sent_stock', [])
                customer_email = order_data.get('customer_email', '')
                
                # Prepare template context
                context = {
                    'shop_name': shop_name,
                    'order_id': order_id,
                    'order_items': order_items,
                    'order_total': order_total,
                    'final_amount': final_amount,
                    'discount_amount': discount_amount,
                    'sent_stock': sent_stock,
                    'customer_email': customer_email,
                    'delivery_date': datetime.now().strftime('%B %d, %Y at %I:%M %p UTC'),
                    'invoice_date': datetime.now().strftime('%B %d, %Y'),
                    'now': datetime.utcnow()
                }
                
                # Render template with context
                html_content = template.render(context)
                return subject, html_content
        
        except Exception as e:
            logger.warning(f"Could not load/render invoice template: {e}, using fallback")
        
        # Fallback inline HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invoice</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #2563eb;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f8fafc;
                    padding: 30px;
                    border-radius: 0 0 8px 8px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📄 Invoice</h1>
                <p>{shop_name}</p>
            </div>
            
            <div class="content">
                <p>Please find your invoice attached as a PDF document.</p>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Generated:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}</p>
                
                <p>Thank you for your business!</p>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    def get_support_email_content(self, user_email, subject, message):
        """
        Generate support request email content.
        
        Args:
            user_email (str): Email address of the user submitting the request
            subject (str): Subject of the support request
            message (str): Message content from the user
            
        Returns:
            tuple: (subject, html_content)
        """
        email_subject = f"🆘 Support Request: {subject} | ShopsyPro"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Support Request</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .email-container {{
                    background-color: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .shopsy-logo {{
                    font-size: 28px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .support-details {{
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 20px;
                    margin: 20px 0;
                    border-radius: 0 5px 5px 0;
                }}
                .message-box {{
                    background: #fff;
                    border: 1px solid #e9ecef;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    white-space: pre-wrap;
                    font-family: 'Courier New', monospace;
                    background-color: #f8f9fa;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }}
                .logo {{
                    font-size: 24px;
                    margin-bottom: 10px;
                }}
                .label {{
                    font-weight: bold;
                    color: #495057;
                    margin-bottom: 5px;
                }}
                .value {{
                    color: #6c757d;
                    margin-bottom: 15px;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="shopsy-logo">ShopsyPro</div>
                    <p>New Support Request</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #333; margin-bottom: 20px;">🆘 Support Request Received</h2>
                    
                    <p>A new support request has been submitted through the ShopsyPro platform.</p>
                    
                    <div class="support-details">
                        <div class="label">From:</div>
                        <div class="value">{user_email}</div>
                        
                        <div class="label">Subject:</div>
                        <div class="value">{subject}</div>
                        
                        <div class="label">Submitted:</div>
                        <div class="value">{datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}</div>
                    </div>
                    
                    <h3 style="color: #333; margin: 30px 0 15px 0;">Message:</h3>
                    <div class="message-box">
{message}
                    </div>
                    
                    <p style="margin-top: 30px; color: #6c757d;">
                        <strong>Note:</strong> This is an automated notification from the ShopsyPro support system. 
                        Please respond directly to the user's email address if a response is required.
                    </p>
                </div>
                
                <div class="footer">
                    <div class="logo">ShopsyPro</div>
                    <p>This is an automated email from ShopsyPro support system.<br>Sent from: noreply@shopsy.pro</p>
                    <p style="margin-top: 15px;">
                        <a href="#" style="color: #667eea; text-decoration: none;">Privacy Policy</a> | 
                        <a href="#" style="color: #667eea; text-decoration: none;">Terms of Service</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return email_subject, html_content

    def create_support_email(self, customer_email, issue_type, subject, message, order_details=None):
        """
        Generate orders-specific support request email content.
        
        Args:
            customer_email (str): Email address of the customer
            issue_type (str): Type of issue (delivery, product, payment, etc.)
            subject (str): Subject of the support request
            message (str): Message content from the customer
            order_details (list): List of order details if specific orders are selected
            
        Returns:
            str: HTML content for the email
        """
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Order Support Request</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 700px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .email-container {{
                    background-color: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .shopsy-logo {{
                    font-size: 28px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .support-details {{
                    background: #f8f9fa;
                    border-left: 4px solid #667eea;
                    padding: 20px;
                    margin: 20px 0;
                    border-radius: 0 5px 5px 0;
                }}
                .message-box {{
                    background: #fff;
                    border: 1px solid #e9ecef;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                    white-space: pre-wrap;
                    font-family: 'Segoe UI', sans-serif;
                    background-color: #f8f9fa;
                }}
                .orders-section {{
                    background: #e3f2fd;
                    border: 1px solid #bbdefb;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .order-item {{
                    background: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 15px;
                    margin: 10px 0;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }}
                .logo {{
                    font-size: 24px;
                    margin-bottom: 10px;
                }}
                .label {{
                    font-weight: bold;
                    color: #495057;
                    margin-bottom: 5px;
                }}
                .value {{
                    color: #6c757d;
                    margin-bottom: 15px;
                }}
                .issue-badge {{
                    display: inline-block;
                    background: #667eea;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: bold;
                    text-transform: uppercase;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <div class="shopsy-logo">ShopsyPro</div>
                    <p>Order Support Request</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #333; margin-bottom: 20px;">🆘 Order Support Request</h2>
                    
                    <p>A customer has submitted a support request related to their orders.</p>
                    
                    <div class="support-details">
                        <div class="label">Customer Email:</div>
                        <div class="value">{customer_email}</div>
                        
                        <div class="label">Issue Type:</div>
                        <div class="value">
                            <span class="issue-badge">{issue_type.title()}</span>
                        </div>
                        
                        <div class="label">Subject:</div>
                        <div class="value">{subject}</div>
                        
                        <div class="label">Submitted:</div>
                        <div class="value">{datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')}</div>
                    </div>
                    
                    <h3 style="color: #333; margin: 30px 0 15px 0;">Customer Message:</h3>
                    <div class="message-box">
{message}
                    </div>
                    """
        
        if order_details:
            html_content += f"""
                    <div class="orders-section">
                        <h3 style="color: #1976d2; margin: 0 0 15px 0;">📦 Related Orders:</h3>
                        <p style="margin-bottom: 15px; color: #666;">The customer has selected the following orders for this support request:</p>
            """
            
            for order in order_details:
                html_content += f"""
                        <div class="order-item">
                            <div style="font-weight: bold; color: #333; margin-bottom: 8px;">
                                Order #{order['order_id']}
                            </div>
                            <div style="color: #666; font-size: 14px;">
                                <div><strong>Shop:</strong> {order['shop_name']} (@{order['shop_username']})</div>
                                <div><strong>Amount:</strong> ${order['total_amount']:.2f}</div>
                                <div><strong>Date:</strong> {order['created_at']}</div>
                            </div>
                        </div>
                """
            
            html_content += """
                    </div>
            """
        else:
            html_content += """
                    <div class="orders-section">
                        <h3 style="color: #1976d2; margin: 0 0 15px 0;">📦 Related Orders:</h3>
                        <p style="margin-bottom: 15px; color: #666; font-style: italic;">
                            No specific orders selected - this is a general support request.
                        </p>
                    </div>
            """
        
        html_content += f"""
                    
                    <p style="margin-top: 30px; color: #6c757d;">
                        <strong>Note:</strong> This is an automated notification from the ShopsyPro order support system. 
                        Please respond directly to the customer's email address if a response is required.
                    </p>
                </div>
                
                <div class="footer">
                    <div class="logo">ShopsyPro</div>
                    <p>This is an automated email from ShopsyPro order support system.<br>Sent from: noreply@shopsy.pro</p>
                    <p style="margin-top: 15px;">
                        <a href="#" style="color: #667eea; text-decoration: none;">Privacy Policy</a> | 
                        <a href="#" style="color: #667eea; text-decoration: none;">Terms of Service</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content


# Global email templates instance
email_templates = EmailTemplates() 