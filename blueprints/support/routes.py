from flask import render_template, request, flash, redirect, url_for, jsonify, session
from . import support
from core.email.client import ses_client
from core.email.templates import email_templates
from models.support_ticket import SupportTicket
from blueprints.auth.decorators import login_required, check_ban_status
from core.cloudflare.verifier import CloudflareVerifier
import logging

logger = logging.getLogger(__name__)

def get_client_ip():
    """Get the real client IP address, handling proxies and load balancers"""
    # Check for forwarded headers in order of preference
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    # Fallback to remote_addr
    return request.remote_addr

@support.route('/tickets')
@login_required
@check_ban_status
def merchant_tickets():
    """Merchant tickets page - shows all support tickets for the logged-in merchant"""
    user_id = session['user_id']
    return render_template('merchant/tickets.html', merchant_id=user_id)

@support.route('/support', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        captcha_token = request.form.get('captcha_token')
        
        if not email or not subject or not message:
            flash('Please fill in all required fields.', 'error')
            return render_template('_base/support.html')
        
        if not captcha_token:
            flash('Please complete the captcha verification.', 'error')
            return render_template('_base/support.html')
        
        # Verify captcha
        client_ip = get_client_ip()
        captcha_result = CloudflareVerifier.verify_token(captcha_token, client_ip)
        
        if not captcha_result.get('success'):
            logger.warning(f"Captcha verification failed for support form from email {email}, IP {client_ip}")
            flash('Captcha verification failed. Please try again.', 'error')
            return render_template('_base/support.html')
        
        # Send email using existing email functions
        try:
            # Generate email content using template
            email_subject, html_content = email_templates.get_support_email_content(
                user_email=email,
                subject=subject,
                message=message
            )
            
            # Send email using SES client
            success = ses_client.send_email(
                to_email='s.archish@icloud.com',
                subject=email_subject,
                html_content=html_content
            )
            
            if success:
                logger.info(f"Support email sent successfully from {email} to s.archish@icloud.com")
                flash('Thank you for your message! We\'ll get back to you within 24 hours.', 'success')
                return redirect(url_for('support.contact'))
            else:
                logger.error(f"Failed to send support email from {email}")
                flash('Sorry, there was an error sending your message. Please try again later.', 'error')
                return render_template('_base/support.html')
            
        except Exception as e:
            logger.error(f"Error sending support email: {e}", exc_info=True)
            flash('Sorry, there was an error sending your message. Please try again later.', 'error')
            return render_template('_base/support.html')
    
    return render_template('_base/support.html')

@support.route('/api/tickets', methods=['POST'])
def create_ticket():
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    merchant_id = data.get('merchant_id')
    customer_id = data.get('customer_id')
    shop_id = data.get('shop_id')
    order_ids = data.get('order_ids', [])
    subject = data.get('subject')
    description = data.get('description')
    
    if not (merchant_id and customer_id and shop_id and order_ids and subject and description):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        ticket = SupportTicket.create(
            merchant_id=merchant_id,
            customer_id=customer_id,
            shop_id=shop_id,
            order_ids=order_ids,
            subject=subject,
            description=description
        )
        return jsonify({'success': True, 'ticket': str(ticket['_id'])})
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to create ticket'}), 500

@support.route('/api/tickets/merchant/<merchant_id>', methods=['GET'])
def get_tickets_by_merchant(merchant_id):
    try:
        tickets = SupportTicket.get_by_merchant(merchant_id)
        for t in tickets:
            t['_id'] = str(t['_id'])
        return jsonify({'tickets': tickets})
    except Exception as e:
        logger.error(f"Error fetching tickets for merchant {merchant_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to fetch tickets'}), 500

@support.route('/api/tickets/customer/<customer_id>', methods=['GET'])
def get_tickets_by_customer(customer_id):
    try:
        tickets = SupportTicket.get_by_customer(customer_id)
        for t in tickets:
            t['_id'] = str(t['_id'])
        return jsonify({'tickets': tickets})
    except Exception as e:
        logger.error(f"Error fetching tickets for customer {customer_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to fetch tickets'}), 500

@support.route('/api/tickets/<ticket_id>', methods=['GET'])
def get_ticket(ticket_id):
    try:
        ticket = SupportTicket.get_by_id_with_stock(ticket_id)  # Use the new method
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
        ticket['_id'] = str(ticket['_id'])
        return jsonify({'ticket': ticket})
    except Exception as e:
        logger.error(f"Error fetching ticket {ticket_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to fetch ticket'}), 500

@support.route('/api/tickets/<ticket_id>/reply', methods=['POST'])
def add_reply(ticket_id):
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    sender = data.get('sender')  # 'customer' or 'merchant'
    message = data.get('message')
    
    if not (sender and message):
        return jsonify({'success': False, 'error': 'Missing sender or message'}), 400
    
    if sender not in ['customer', 'merchant']:
        return jsonify({'success': False, 'error': 'Invalid sender type'}), 400
    
    try:
        ticket = SupportTicket.add_reply(ticket_id, sender, message)
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        ticket['_id'] = str(ticket['_id'])
        return jsonify({'success': True, 'ticket': ticket})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error adding reply to ticket {ticket_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to add reply'}), 500

@support.route('/api/tickets/<ticket_id>/mark_read', methods=['POST'])
def mark_ticket_read(ticket_id):
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    user_type = data.get('user_type')  # 'merchant' or 'customer'
    
    if user_type not in ['merchant', 'customer']:
        return jsonify({'success': False, 'error': 'Invalid user_type'}), 400
    
    try:
        SupportTicket.mark_read(ticket_id, user_type)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error marking ticket {ticket_id} as read: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to mark ticket as read'}), 500

# NEW ROUTES FOR TICKET STATUS MANAGEMENT

@support.route('/api/tickets/<ticket_id>/status', methods=['PUT'])
def update_ticket_status(ticket_id):
    """Update ticket status (open/closed)"""
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    status = data.get('status')
    
    if not status:
        return jsonify({'success': False, 'error': 'Missing status'}), 400
    
    if status not in ['open', 'closed']:
        return jsonify({'success': False, 'error': 'Invalid status. Must be "open" or "closed"'}), 400
    
    try:
        ticket = SupportTicket.update_status(ticket_id, status)
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        logger.info(f"Ticket {ticket_id} status updated to {status}")
        return jsonify({'success': True, 'ticket': ticket})
    except Exception as e:
        logger.error(f"Error updating ticket {ticket_id} status: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to update ticket status'}), 500

@support.route('/api/tickets/<ticket_id>/close', methods=['POST'])
def close_ticket(ticket_id):
    """Close a specific ticket"""
    try:
        ticket = SupportTicket.update_status(ticket_id, 'closed')
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        logger.info(f"Ticket {ticket_id} closed")
        return jsonify({'success': True, 'ticket': ticket})
    except Exception as e:
        logger.error(f"Error closing ticket {ticket_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to close ticket'}), 500

@support.route('/api/tickets/<ticket_id>/reopen', methods=['POST'])
def reopen_ticket(ticket_id):
    """Reopen a closed ticket"""
    try:
        ticket = SupportTicket.update_status(ticket_id, 'open')
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        logger.info(f"Ticket {ticket_id} reopened")
        return jsonify({'success': True, 'ticket': ticket})
    except Exception as e:
        logger.error(f"Error reopening ticket {ticket_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to reopen ticket'}), 500

@support.route('/api/tickets/<ticket_id>', methods=['PATCH'])
def patch_ticket(ticket_id):
    """Update ticket via PATCH method (alternative endpoint)"""
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    status = data.get('status')
    
    if not status:
        return jsonify({'success': False, 'error': 'Missing status'}), 400
    
    if status not in ['open', 'closed']:
        return jsonify({'success': False, 'error': 'Invalid status. Must be "open" or "closed"'}), 400
    
    try:
        ticket = SupportTicket.update_status(ticket_id, status)
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        logger.info(f"Ticket {ticket_id} status updated to {status} via PATCH")
        return jsonify({'success': True, 'ticket': ticket})
    except Exception as e:
        logger.error(f"Error updating ticket {ticket_id} via PATCH: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to update ticket'}), 500

# BULK OPERATIONS FOR MULTIPLE TICKETS

@support.route('/api/tickets/bulk/close', methods=['POST'])
def bulk_close_tickets():
    """Close multiple tickets at once"""
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    ticket_ids = data.get('ticket_ids', [])
    
    if not ticket_ids:
        return jsonify({'success': False, 'error': 'No ticket IDs provided'}), 400
    
    try:
        results = []
        for ticket_id in ticket_ids:
            try:
                ticket = SupportTicket.update_status(ticket_id, 'closed')
                if ticket:
                    results.append({'ticket_id': ticket_id, 'success': True})
                else:
                    results.append({'ticket_id': ticket_id, 'success': False, 'error': 'Ticket not found'})
            except Exception as e:
                results.append({'ticket_id': ticket_id, 'success': False, 'error': str(e)})
        
        successful = len([r for r in results if r['success']])
        logger.info(f"Bulk close operation: {successful}/{len(ticket_ids)} tickets closed successfully")
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': len(ticket_ids),
                'successful': successful,
                'failed': len(ticket_ids) - successful
            }
        })
    except Exception as e:
        logger.error(f"Error in bulk close operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to close tickets'}), 500

@support.route('/api/tickets/bulk/reopen', methods=['POST'])
def bulk_reopen_tickets():
    """Reopen multiple tickets at once"""
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    ticket_ids = data.get('ticket_ids', [])
    
    if not ticket_ids:
        return jsonify({'success': False, 'error': 'No ticket IDs provided'}), 400
    
    try:
        results = []
        for ticket_id in ticket_ids:
            try:
                ticket = SupportTicket.update_status(ticket_id, 'open')
                if ticket:
                    results.append({'ticket_id': ticket_id, 'success': True})
                else:
                    results.append({'ticket_id': ticket_id, 'success': False, 'error': 'Ticket not found'})
            except Exception as e:
                results.append({'ticket_id': ticket_id, 'success': False, 'error': str(e)})
        
        successful = len([r for r in results if r['success']])
        logger.info(f"Bulk reopen operation: {successful}/{len(ticket_ids)} tickets reopened successfully")
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': len(ticket_ids),
                'successful': successful,
                'failed': len(ticket_ids) - successful
            }
        })
    except Exception as e:
        logger.error(f"Error in bulk reopen operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to reopen tickets'}), 500

@support.route('/api/tickets/bulk/mark_read', methods=['POST'])
def bulk_mark_read():
    """Mark multiple tickets as read"""
    if not request.is_json or request.json is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400
    
    data = request.json
    ticket_ids = data.get('ticket_ids', [])
    user_type = data.get('user_type')
    
    if not ticket_ids:
        return jsonify({'success': False, 'error': 'No ticket IDs provided'}), 400
    
    if user_type not in ['merchant', 'customer']:
        return jsonify({'success': False, 'error': 'Invalid user_type'}), 400
    
    try:
        results = []
        for ticket_id in ticket_ids:
            try:
                SupportTicket.mark_read(ticket_id, user_type)
                results.append({'ticket_id': ticket_id, 'success': True})
            except Exception as e:
                results.append({'ticket_id': ticket_id, 'success': False, 'error': str(e)})
        
        successful = len([r for r in results if r['success']])
        logger.info(f"Bulk mark read operation: {successful}/{len(ticket_ids)} tickets marked as read")
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total': len(ticket_ids),
                'successful': successful,
                'failed': len(ticket_ids) - successful
            }
        })
    except Exception as e:
        logger.error(f"Error in bulk mark read operation: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to mark tickets as read'}), 500