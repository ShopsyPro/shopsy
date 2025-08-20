from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
from models import Shop, Order, CustomerOrderTracker, CustomerOTP
from blueprints.auth.decorators import login_required, check_ban_status, customer_session_required
from . import orders_bp
try:
    from core.email import email_service
except ImportError:
    email_service = None
from core.cloudflare.verifier import CloudflareVerifier
import logging
import re
from bson import ObjectId

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

@orders_bp.route('/orders')
@orders_bp.route('/orders/<int:page>')
@login_required
@check_ban_status
def orders(page=1):
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('auth.login'))
    
    # Get query parameters
    sort_by = request.args.get('sort_by', 'date')  # Default sort by date
    sort_order = request.args.get('sort_order', 'desc')  # Default descending
    search_query = request.args.get('search_stock', '').strip()  # Keep parameter name for URL compatibility
    
    # Get all orders
    all_orders = Order.get_by_shop(user_id)
    
    # Filter to only show completed orders
    completed_orders = [order for order in all_orders if order.get('status') == 'completed']
    
    # Apply search filter if provided
    if search_query:
        filtered_orders = []
        search_lower = search_query.lower()
        
        for order in completed_orders:
            order_matches = False
            
            # Search by Order ID (both custom format and ObjectId)
            display_id = Order.get_display_id(order)
            if search_lower in display_id.lower():
                order_matches = True
            
            # Also search by raw ObjectId for backward compatibility
            if search_lower in str(order.get('_id', '')).lower():
                order_matches = True
            
            # Search in sent stock items (existing functionality)
            if not order_matches:
                sent_stock = order.get('sent_stock', [])
                for stock_item in sent_stock:
                    if search_lower in stock_item.get('stock_item', '').lower():
                        order_matches = True
                        break
            
            if order_matches:
                filtered_orders.append(order)
                
        completed_orders = filtered_orders
    
    # Apply sorting
    if sort_by == 'date':
        completed_orders.sort(
            key=lambda x: x.get('created_at', datetime.min), 
            reverse=(sort_order == 'desc')
        )
    elif sort_by == 'total':
        completed_orders.sort(
            key=lambda x: float(x.get('total_amount', 0)), 
            reverse=(sort_order == 'desc')
        )
    
    # Paginate orders - 15 per page
    per_page = 15
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    total_orders = len(completed_orders)
    total_pages = (total_orders + per_page - 1) // per_page  # Ceiling division
    
    # Get current page orders
    paginated_orders = completed_orders[start_idx:end_idx]
    
    return render_template('merchant/orders/orders.html', 
                           orders=paginated_orders,
                           current_page=page,
                           total_pages=total_pages,
                           total_orders=total_orders,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           search_stock=search_query)  # Keep parameter name for template compatibility

@orders_bp.route('/invoice/<order_id>')
@login_required
@check_ban_status
def invoice(order_id):
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.home'))
    
    # Get the order
    order = Order.get_by_id(order_id)
    
    # Check if order exists and belongs to this shop
    if not order or str(order.get('shop_id')) != str(user_id):
        flash('Order not found or access denied', 'error')
        return redirect(url_for('orders.orders'))
    
    # Only show invoices for completed orders
    if order.get('status') != 'completed':
        flash('Invoice is only available for completed orders', 'error')
        return redirect(url_for('orders.orders'))
    
    # Prepare variables for email invoice template
    order_total = order.get('original_total', order.get('total_amount', 0))
    final_amount = order.get('total_amount', 0)
    order_items = order.get('items', [])
    discount_amount = order.get('discount_total', 0)
    shop_name = shop.get('name', 'Shop')
    # PRIVACY FIX: Remove customer email from merchant view
    # customer_email = order.get('customer_email', '')
    sent_stock = order.get('sent_stock', [])
    
    # Get order display ID
    display_order_id = Order.get_display_id(order)
    
    # Calculate dates
    invoice_date = order.get('created_at', datetime.utcnow()).strftime('%B %d, %Y')
    delivery_date = order.get('updated_at', datetime.utcnow()).strftime('%B %d, %Y at %I:%M %p')
    
    return render_template('email/invoice.html', 
                         order=order, 
                         shop=shop,
                         order_total=order_total,
                         final_amount=final_amount,
                         order_items=order_items,
                         discount_amount=discount_amount,
                         shop_name=shop_name,
                         order_id=display_order_id,
                         # PRIVACY FIX: Remove customer email from merchant view
                         # customer_email=customer_email,
                         delivery_date=delivery_date,
                         invoice_date=invoice_date,
                         sent_stock=sent_stock,
                         now=datetime.utcnow())


@orders_bp.route('/track-orders/invoice/<order_id>')
def customer_invoice(order_id):
    # 1) Verify the customer is logged in via OTP
    email = session.get('verified_customer_email')
    if not email:
        flash('Please verify your email first', 'error')
        return redirect(url_for('orders.track_orders'))

    # 2) Load the order and confirm that email matches
    order = Order.get_by_id(order_id)
    if not order or order.get('customer_email') != email:
        flash('Order not found or access denied', 'error')
        return redirect(url_for('orders.customer_orders_dashboard'))

    if order.get('status') != 'completed':
        flash('Invoice only available after completion', 'error')
        return redirect(url_for('orders.customer_orders_dashboard'))

    # 3) Build the exact same context you do for the merchant invoice
    shop = Shop.get_by_id(str(order.get('shop_id')))
    display_id = Order.get_display_id(order)
    invoice_date = order.get('created_at', datetime.utcnow()).strftime('%B %d, %Y')
    delivery_date = order.get('updated_at', datetime.utcnow()).strftime('%B %d, %Y at %I:%M %p')
    return render_template('email/invoice.html',
                           order=order,
                           shop=shop,
                           order_total=order.get('original_total', order.get('total_amount',0)),
                           final_amount=order.get('total_amount',0),
                           order_items=order.get('items',[]),
                           discount_amount=order.get('discount_total',0),
                           shop_name=shop.get('name','Shop'),
                           order_id=display_id,
                           customer_email=email,
                           invoice_date=invoice_date,
                           delivery_date=delivery_date,
                           sent_stock=order.get('sent_stock',[]),
                           now=datetime.utcnow())


@orders_bp.route('/activity-history')
@orders_bp.route('/activity-history/<int:page>')
@login_required
@check_ban_status
def activity_history(page=1):
    user_id = session['user_id']
    
    # Get all activities (without time limit)
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('auth.login'))
    
    # Get all activities from the shop document
    all_activities = []
    if shop and "activity_log" in shop:
        all_activities = shop.get("activity_log", [])
        # Sort by timestamp (newest first)
        all_activities.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Paginate activities - 20 per page
    per_page = 20
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    total_activities = len(all_activities)
    total_pages = (total_activities + per_page - 1) // per_page  # Ceiling division
    
    # Get current page activities
    paginated_activities = all_activities[start_idx:end_idx] if start_idx < total_activities else []
    
    return render_template('merchant/activity/activity_history.html', 
                           activities=paginated_activities,
                           current_page=page,
                           total_pages=total_pages,
                           total_activities=total_activities)

# ================== CUSTOMER ORDER TRACKING SYSTEM ==================

@orders_bp.route('/track-orders')
def track_orders():
    """Customer order tracking - email input page"""
    return render_template('customer/track_orders.html')

@orders_bp.route('/api/track-orders/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to customer email for verification"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Invalid request data'
            }), 400
        
        email = data.get('email', '').strip().lower()
        captcha_token = data.get('captcha_token', '').strip()
        
        if not email:
            return jsonify({
                'success': False,
                'message': 'Email address is required'
            }), 400
        
        if not captcha_token:
            return jsonify({
                'success': False,
                'message': 'Captcha verification is required'
            }), 400
        
        # Verify captcha
        client_ip = get_client_ip()
        captcha_result = CloudflareVerifier.verify_token(captcha_token, client_ip)
        
        if not captcha_result.get('success'):
            logger.warning(f"Captcha verification failed for email {email} from IP {client_ip}")
            return jsonify({
                'success': False,
                'message': 'Captcha verification failed. Please try again.'
            }), 400
        
        # Basic email validation
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({
                'success': False,
                'message': 'Please enter a valid email address'
            }), 400
        
        # Check if this email has any orders
        orders = CustomerOrderTracker.get_orders_by_email(email)
        
        if not orders:
            return jsonify({
                'success': False,
                'message': 'No orders found for this email address'
            }), 404
        
        # Generate and send OTP
        logger.info(f"Attempting to send OTP to {email}")
        
        otp_record = CustomerOTP.create(email)
        logger.info(f"OTP record created for {email}, code: {otp_record.get('otp_code', 'N/A')}")
        
        logger.info(f"Attempting to send OTP email to {email}")
        if email_service:
            otp_sent = email_service.send_customer_otp_email(email, otp_record['otp_code'])
        else:
            otp_sent = False
        logger.info(f"OTP email send result for {email}: {otp_sent}")
        
        if otp_sent:
            logger.info(f"OTP successfully sent to {email}")
            return jsonify({
                'success': True,
                'message': f'Verification code sent to {email}. Please check your email.',
                'expires_in': 7200  # 2 hours in seconds
            })
        else:
            logger.error(f"Failed to send OTP email to {email}")
            return jsonify({
                'success': False,
                'message': 'Failed to send verification email. Please try again.'
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending OTP to {email}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An error occurred. Please try again.'
        }), 500

@orders_bp.route('/track-orders/verify')
def verify_otp_page():
    """OTP verification page"""
    email = request.args.get('email', '')
    return render_template('customer/verify_otp.html', email=email)

@orders_bp.route('/api/track-orders/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP code"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Invalid request data'
            }), 400
        
        email = data.get('email', '').strip().lower()
        otp_code = data.get('otp_code', '').strip()
        
        if not email or not otp_code:
            return jsonify({
                'success': False,
                'message': 'Email and OTP code are required'
            }), 400
        
        # Verify OTP
        result = CustomerOTP.verify(email, otp_code)
        
        if result['success']:
            # Store verified email in session with correct keys
            session['customer_email'] = email
            session['customer_otp_verified'] = True
            session['customer_otp_timestamp'] = int(datetime.utcnow().timestamp())
            
            return jsonify({
                'success': True,
                'message': 'Email verified successfully',
                'redirect_url': '/track-orders/dashboard'
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            }), 400
            
    except Exception as e:
        logger.error(f"Error verifying OTP for email {data.get('email', 'unknown')}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An error occurred during verification. Please try again.'
        }), 500

@orders_bp.route('/api/track-orders/otp-time-remaining', methods=['POST'])
def get_otp_time_remaining():
    """Get remaining time for OTP verification"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Invalid request data'
            }), 400
        
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({
                'success': False,
                'message': 'Email is required'
            }), 400
        
        otp_record = CustomerOTP.get_by_email(email)
        
        if not otp_record:
            return jsonify({
                'success': False,
                'expired': True,
                'remaining_seconds': 0
            })
        
        # Calculate remaining time
        created_at = otp_record.get('created_at')
        expires_at = created_at + timedelta(hours=2)  # 2 hour expiry
        now = datetime.utcnow()
        
        if now >= expires_at:
            return jsonify({
                'success': True,
                'expired': True,
                'remaining_seconds': 0
            })
        
        remaining_seconds = int((expires_at - now).total_seconds())
        
        return jsonify({
            'success': True,
            'expired': False,
            'remaining_seconds': remaining_seconds
        })
        
    except Exception as e:
        logger.error(f"Error checking OTP time for email {data.get('email', 'unknown')}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'Error checking OTP status'
        }), 500

@orders_bp.route('/track-orders/dashboard')
@customer_session_required
def customer_orders_dashboard():
    """Customer orders dashboard - requires verified email session"""
    # Session validation is handled by the decorator
    customer_email = session.get('customer_email')
    
    # Caching logic
    refresh = request.args.get('refresh') == '1'
    orders_cache = session.get('customer_orders_cache')
    if not orders_cache or refresh:
        all_orders = CustomerOrderTracker.get_orders_by_email(customer_email)
        stats = CustomerOrderTracker.get_order_stats(customer_email)
        def convert_objectids_to_strings(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, ObjectId):
                        obj[key] = str(value)
                    elif isinstance(value, (dict, list)):
                        convert_objectids_to_strings(value)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if isinstance(item, ObjectId):
                        obj[i] = str(item)
                    elif isinstance(item, (dict, list)):
                        convert_objectids_to_strings(item)
        convert_objectids_to_strings(all_orders)
        orders_cache = {
            'all_orders': all_orders,
            'stats': stats
        }
        session['customer_orders_cache'] = orders_cache
    else:
        all_orders = orders_cache['all_orders']
        stats = orders_cache['stats']
    page = int(request.args.get('page', 1))
    per_page = 10
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    total_orders = len(all_orders)
    total_pages = (total_orders + per_page - 1) // per_page
    paginated_orders = all_orders[start_idx:end_idx]
    return render_template('order/customer/orders_dashboard.html', 
                           orders=paginated_orders,
                           all_orders=all_orders,  # Pass all orders for support
                           stats=stats,
                           customer_email=customer_email,
                           current_page=page,
                           total_pages=total_pages,
                           total_orders=total_orders)

@orders_bp.route('/api/track-orders/extend-session', methods=['POST'])
def extend_customer_session():
    """Extend customer verification session"""
    customer_email = session.get('customer_email')
    customer_otp_verified = session.get('customer_otp_verified', False)
    
    if not customer_email or not customer_otp_verified:
        return jsonify({
            'success': False,
            'message': 'No active session found'
        }), 401
    
    # Check if session has expired (30 minutes)
    otp_timestamp = session.get('customer_otp_timestamp')
    if otp_timestamp:
        otp_time = datetime.fromtimestamp(otp_timestamp)
        if datetime.utcnow() - otp_time > timedelta(minutes=30):
            # Session expired, clear session data
            session.pop('customer_email', None)
            session.pop('customer_otp_verified', None)
            session.pop('customer_orders', None)
            session.pop('customer_otp_timestamp', None)
            return jsonify({
                'success': False,
                'message': 'Session expired'
            }), 401
    
    # Check OTP verification in database
    if CustomerOTP.is_verified(customer_email):
        # Extend session
        session['customer_otp_timestamp'] = int(datetime.utcnow().timestamp())
        session.modified = True
        return jsonify({
            'success': True,
            'message': 'Session extended successfully'
        })
    else:
        # Clear session data
        session.pop('customer_email', None)
        session.pop('customer_otp_verified', None)
        session.pop('customer_orders', None)
        session.pop('customer_otp_timestamp', None)
        return jsonify({
            'success': False,
            'message': 'Verification expired. Please verify again.'
        }), 401

@orders_bp.route('/api/orders-support', methods=['POST'])
def orders_support():
    """Handle orders-specific support requests"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'Invalid request data'
            }), 400
        
        customer_email = data.get('customer_email', '').strip().lower()
        issue_type = data.get('issue_type', '').strip()
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        selected_orders = data.get('selected_orders', [])
        
        if not customer_email or not issue_type or not subject or not message:
            return jsonify({
                'success': False,
                'message': 'All fields are required'
            }), 400
        
        # Verify customer email matches session
        session_email = session.get('customer_email')
        if not session_email or session_email != customer_email:
            return jsonify({
                'success': False,
                'message': 'Unauthorized access'
            }), 401
        
        # Get order details for selected orders
        order_details = []
        if selected_orders:
            orders = CustomerOrderTracker.get_orders_by_email(customer_email)
            for order in orders:
                # Convert ObjectId to string for comparison
                order_id = str(order.get('_id')) if order.get('_id') else None
                if order_id in selected_orders:
                    order_details.append({
                        'order_id': order.get('order_summary', {}).get('display_id', 'N/A'),
                        'shop_name': order.get('shop_name', 'Unknown Shop'),
                        'shop_username': order.get('shop_username', 'unknown'),
                        'total_amount': order.get('total_amount', 0),
                        'created_at': order.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if order.get('created_at') else 'N/A'
                    })
        
        # Prepare email content
        email_content = f"""
        <h2>Order Support Request</h2>
        <p><strong>Customer Email:</strong> {customer_email}</p>
        <p><strong>Issue Type:</strong> {issue_type.title()}</p>
        <p><strong>Subject:</strong> {subject}</p>
        <p><strong>Message:</strong></p>
        <p>{message}</p>
        """
        
        if order_details:
            email_content += f"""
            <h3>Selected Orders:</h3>
            <ul>
            """
            for order in order_details:
                email_content += f"""
                <li>
                    <strong>Order #{order['order_id']}</strong><br>
                    Shop: {order['shop_name']} (@{order['shop_username']})<br>
                    Amount: ${order['total_amount']:.2f}<br>
                    Date: {order['created_at']}
                </li>
                """
            email_content += "</ul>"
        else:
            email_content += "<p><em>No specific orders selected - general support request</em></p>"
        
        # Send email using existing email client
        from core.email.client import SESClient
        from core.email.templates import EmailTemplates
        
        email_client = SESClient()
        email_templates = EmailTemplates()
        
        # Create support email template
        support_template = email_templates.create_support_email(
            customer_email=customer_email,
            issue_type=issue_type,
            subject=subject,
            message=message,
            order_details=order_details
        )
        
        # Send email
        success = email_client.send_email(
            to_email='s.archish@icloud.com',
            subject=f'Order Support Request: {subject}',
            html_content=support_template
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Support request sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send support request'
            }), 500
            
    except Exception as e:
        logger.error(f"Error processing orders support request: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An error occurred while processing your request'
        }), 500

@orders_bp.route('/track-orders/support')
@customer_session_required
def customer_orders_support_page():
    """Customer orders support page - requires verified email session"""
    # Session validation is handled by the decorator
    customer_email = session.get('customer_email')
    
    refresh = request.args.get('refresh') == '1'
    orders_cache = session.get('customer_orders_cache')
    if not orders_cache or refresh:
        all_orders = CustomerOrderTracker.get_orders_by_email(customer_email)
        def convert_objectids_to_strings(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, ObjectId):
                        obj[key] = str(value)
                    elif isinstance(value, (dict, list)):
                        convert_objectids_to_strings(value)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if isinstance(item, ObjectId):
                        obj[i] = str(item)
                    elif isinstance(item, (dict, list)):
                        convert_objectids_to_strings(item)
        convert_objectids_to_strings(all_orders)
        # Only cache orders for support page
        if orders_cache:
            session['customer_orders_cache']['all_orders'] = all_orders
        else:
            session['customer_orders_cache'] = {'all_orders': all_orders, 'stats': {}}
    else:
        all_orders = orders_cache['all_orders']
    return render_template('customer/orders_support.html', 
                           all_orders=all_orders,
                           customer_email=customer_email)

@orders_bp.route('/track-orders/tickets')
@customer_session_required
def customer_tickets_page():
    """Customer tickets page - requires verified email session"""
    # Session validation is handled by the decorator
    customer_email = session.get('customer_email')
    
    return render_template('customer/my_tickets.html', 
                           customer_email=customer_email)

@orders_bp.route('/track-orders/logout')
def customer_logout():
    # Clear all customer-related session data
    session.pop('verified_customer_email', None)
    session.pop('verification_time', None)
    session.pop('customer_orders_cache', None)
    session.pop('customer_email', None)
    session.pop('customer_otp_verified', None)
    session.pop('customer_orders', None)
    session.pop('customer_otp_timestamp', None)
    
    flash('You have been logged out from order tracking.', 'info')
    
    # Add cache-busting parameter to prevent back navigation
    import time
    timestamp = int(time.time())
    return redirect(url_for('orders.track_orders') + f'?_t={timestamp}') 