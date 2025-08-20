"""
PDF generation module for email attachments.

This module handles the generation of PDF invoices and other documents
that can be attached to emails.
"""

import io
from datetime import datetime
import logging
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)


class PDFGenerator:
    """PDF generation utilities for email attachments."""
    
    def __init__(self):
        """Initialize PDF generator."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Set up custom styles for PDF generation."""
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c3e50')
        )
        
        self.header_style = ParagraphStyle(
            'CustomHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#34495e')
        )
        
        self.normal_style = ParagraphStyle(
            'CustomNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6
        )
    
    def generate_invoice_pdf(self, order_data, shop_name):
        """
        Generate a PDF invoice for an order.
        
        Args:
            order_data (dict): Order data containing order details
            shop_name (str): Name of the shop
            
        Returns:
            bytes: PDF content as bytes
        """
        try:
            # Create PDF buffer
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=letter, 
                rightMargin=72, 
                leftMargin=72, 
                topMargin=72, 
                bottomMargin=18
            )
            
            # Build PDF content
            story = []
            
            # Title
            title = Paragraph("INVOICE", self.title_style)
            story.append(title)
            story.append(Spacer(1, 12))
            
            # Shop and Order info
            shop_info = f"<b>{shop_name}</b><br/>Shopsy.Pro Platform"
            story.append(Paragraph(shop_info, self.normal_style))
            story.append(Spacer(1, 12))
            
            # Get display order ID
            display_order_id = self._get_display_order_id(order_data)
            
            order_info = f"<b>Order ID:</b> {display_order_id}<br/>"
            order_info += f"<b>Date:</b> {order_data.get('created_at', datetime.utcnow()).strftime('%B %d, %Y at %I:%M %p')}<br/>"
            order_info += f"<b>Status:</b> {order_data.get('status', 'Unknown').title()}<br/>"
            if order_data.get('customer_email'):
                order_info += f"<b>Customer:</b> {order_data.get('customer_email')}"
            
            story.append(Paragraph(order_info, self.normal_style))
            story.append(Spacer(1, 20))
            
            # Order items table
            story.append(Paragraph("Order Items", self.header_style))
            
            # Create and add items table
            items_table = self._create_items_table(order_data)
            story.append(items_table)
            story.append(Spacer(1, 20))
            
            # Payment status
            payment_status = self._get_payment_status(order_data)
            story.append(Paragraph(payment_status, self.header_style))
            story.append(Spacer(1, 12))
            
            # Footer
            footer_text = "Thank you for your business!<br/>This is an automated invoice from Shopsy.Pro"
            story.append(Paragraph(footer_text, self.normal_style))
            
            # Build PDF
            doc.build(story)
            
            # Get PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            
            logger.info(f"PDF invoice generated successfully for order {display_order_id}")
            return pdf_content
            
        except Exception as e:
            logger.error(f"Failed to generate PDF invoice: {str(e)}")
            return None
    
    def _get_display_order_id(self, order_data):
        """Get the display order ID from order data."""
        # Use the order_id parameter which is now the display ID from caller
        # First try the new format field, fallback to the display ID calculation
        display_order_id = order_data.get('order_id')  # This is the new format field
        if not display_order_id:
            # Fallback for old orders - import Order class to use get_display_id
            try:
                from models import Order
                display_order_id = Order.get_display_id(order_data)
            except:
                display_order_id = str(order_data.get('_id', 'N/A'))[:8]
        return display_order_id
    
    def _create_items_table(self, order_data):
        """Create the order items table for the PDF."""
        # Create table data
        table_data = [['Product', 'Quantity', 'Price', 'Total']]
        
        for item in order_data.get('items', []):
            product_name = item.get('name', 'Unknown Product')
            quantity = item.get('quantity', 1)
            price = f"${item.get('price', 0):.2f}"
            total = f"${item.get('price', 0) * quantity:.2f}"
            
            table_data.append([product_name, str(quantity), price, total])
        
        # Add discount row if applicable
        discount_amount = order_data.get('discount_amount', 0)
        if discount_amount > 0:
            table_data.append(['', '', 'Discount:', f"-${discount_amount:.2f}"])
        
        # Add total row
        table_data.append(['', '', 'Total:', f"${order_data.get('total_amount', 0):.2f}"])
        
        # Create table
        table = Table(table_data, colWidths=[3*inch, 1*inch, 1*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            # Make total row bold
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
        ]))
        
        return table
    
    def _get_payment_status(self, order_data):
        """Get payment status text for the PDF."""
        sent_stock = order_data.get('sent_stock', [])
        if sent_stock:
            return "✅ Payment Status: Completed & Products Delivered"
        else:
            return "⏳ Payment Status: Completed - Products Pending Delivery"


# Global PDF generator instance
pdf_generator = PDFGenerator() 