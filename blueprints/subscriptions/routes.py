"""
Subscription routes for handling merchant subscription operations.
"""

from flask import render_template, session, redirect, url_for, request, jsonify, flash
from datetime import datetime, timedelta
from models import Subscription, Shop
from blueprints.auth.decorators import login_required, check_ban_status
from core.cryptomus import CryptomusClient
from . import subscriptions_bp
import json
import os
from bson import ObjectId

@subscriptions_bp.route('/upgrade')
@login_required
@check_ban_status
def upgrade():
    """Show upgrade page with subscription options"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.dashboard'))
    
    # Check if merchant has active subscription
    active_subscription = Subscription.get_active_subscription(user_id)
    
    # Check if merchant has pending subscription
    pending_subscription = Subscription.get_pending_subscription(user_id)
    
    context = {
        'shop': shop,
        'is_paid': shop.get('is_paid', False),
        'active_subscription': active_subscription,
        'pending_subscription': pending_subscription,
        'now': datetime.utcnow()
    }
    
    return render_template('merchant/subscriptions/upgrade.html', **context)

@subscriptions_bp.route('/create', methods=['POST'])
@login_required
@check_ban_status
def create_subscription():
    """Create a new subscription payment"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return jsonify({'error': 'Shop not found'}), 404
    
    # Get form data
    currency = request.form.get('currency', 'USDT').upper()
    
    # Define subscription pricing in USD (Cryptomus will handle conversion)
    subscription_price_usd = 1.0  # $25 USD for Premium plan
    
    # Supported currencies
    supported_currencies = ['BTC', 'USDT', 'BNB']
    
    if currency not in supported_currencies:
        return jsonify({'error': 'Unsupported currency'}), 400
    
    # Check if merchant already has pending subscription
    pending_subscription = Subscription.get_pending_subscription(user_id)
    if pending_subscription:
        return jsonify({
            'error': 'You already have a pending subscription. Please complete or wait for it to expire.',
            'payment_link': pending_subscription.get('payment_link')
        }), 400
    
    # SECURITY: Check if merchant already has active subscription
    active_subscription = Subscription.get_active_subscription(user_id)
    if active_subscription:
        return jsonify({
            'error': 'You already have an active Premium subscription.',
            'expires_at': active_subscription['ends_at'].isoformat()
        }), 400
    
    try:
        # Initialize Cryptomus client
        cryptomus = CryptomusClient()
        
        # Generate unique order ID
        order_id = f"SUB_{shop['merchant_code']}_{int(datetime.utcnow().timestamp())}"
        
        # Create payment with Cryptomus
        callback_url = url_for('subscriptions.webhook', _external=True)
        success_url = url_for('subscriptions.success', _external=True)
        return_url = url_for('subscriptions.upgrade', _external=True)
        
        # Use USD amount and target currency - Cryptomus will handle conversion
        payment_response = cryptomus.create_payment(
            amount=subscription_price_usd,
            order_id=order_id,
            currency='USD',  # Source currency (what we're charging)
            to_currency=currency,  # Target cryptocurrency
            callback_url=callback_url,
            url_success=success_url,
            url_return=return_url,
            buyer_email=shop['owner']['email']
        )
        
        if payment_response.get('state') == 0:  # Success
            result = payment_response.get('result', {})
            payment_link = result.get('url')
            crypto_invoice_id = result.get('uuid')
            
            # Get the actual crypto amount from Cryptomus response
            crypto_amount = result.get('amount', subscription_price_usd)
            
            # Create subscription record
            subscription = Subscription.create(
                merchant_id=user_id,
                currency=currency,
                amount=crypto_amount,  # Store the actual crypto amount
                payment_link=payment_link,
                crypto_invoice_id=crypto_invoice_id
            )
            
            return jsonify({
                'success': True,
                'payment_link': payment_link,
                'subscription_id': str(subscription['_id']),
                'expires_at': subscription['expires_at'].isoformat()
            })
        else:
            return jsonify({
                'error': 'Failed to create payment',
                'details': payment_response.get('message', 'Unknown error')
            }), 500
            
    except Exception as e:
        return jsonify({'error': f'Failed to create subscription: {str(e)}'}), 500

@subscriptions_bp.route('/webhook', methods=['POST'])
def webhook():
    """Handle Cryptomus webhook notifications"""
    try:
        # Get the raw JSON data (matching orders webhook)
        payload = request.get_json(force=True)
        if not payload:
            print('Empty subscription webhook payload')
            return 'Empty payload', 400
        
        # Extract signature from payload (matching orders webhook)
        signature = payload.get('sign')
        if not signature:
            print('Missing Cryptomus webhook signature')
            return 'Missing signature', 400
        
        # Remove signature from payload for verification (matching orders webhook)
        payload_for_verification = payload.copy()
        del payload_for_verification['sign']
        
        # Initialize Cryptomus client for signature verification
        cryptomus = CryptomusClient()
        
        # Verify signature (matching orders webhook)
        if not cryptomus.verify_webhook_signature(payload_for_verification, signature):
            print('SECURITY ALERT: Invalid Cryptomus webhook signature!')
            # SECURITY: Enable signature verification in production
            return 'Invalid signature', 403
        
        # Use the verified payload
        data = payload
        
        # Get order information
        order_id = data.get('order_id')
        status = data.get('status')
        uuid = data.get('uuid')
        
        # Log webhook details for debugging
        print(f"Subscription webhook received: order_id={order_id}, status={status}, uuid={uuid}")
        print(f"Full webhook payload: {data}")
        
        if not order_id or not uuid:
            print(f"Missing order_id or uuid in subscription webhook: {data}")
            return 'Missing order_id or uuid', 400
        
        # Find subscription by crypto invoice ID
        subscription = Subscription.get_by_crypto_invoice_id(uuid)
        
        if not subscription:
            print(f"Subscription not found for uuid: {uuid}")
            return 'Subscription not found', 404
        
        # Handle payment status (matching orders webhook pattern)
        if status in ['paid', 'paid_over']:
            # SECURITY: Validate payment amount before marking as paid
            invoice_amount = data.get('amount')  # Amount invoiced by Cryptomus
            payment_amount = data.get('payment_amount')  # Amount actually paid
            expected_usd_amount = 1.0  # Our subscription price in USD
            
            # Log amounts for debugging
            print(f"Invoice amount: {invoice_amount}, Payment amount: {payment_amount}, Expected: {expected_usd_amount}")
            
            # Validate payment amount (allow small overpayment but not underpayment)
            if not payment_amount or float(payment_amount) < (expected_usd_amount * 0.95):  # Allow 5% tolerance
                print(f"SECURITY ALERT: Underpayment detected! Expected: ${expected_usd_amount}, Got: ${payment_amount}")
                Subscription.update_subscription(subscription['_id'], 
                                               status='expired', 
                                               webhook_payload=data)
                return 'Payment amount insufficient', 400
            
            # Mark subscription as paid
            Subscription.mark_as_paid(subscription['_id'], webhook_payload=data)
            
            # Log activity
            Shop.log_activity(
                subscription['merchant_id'], 
                "subscription", 
                "payment", 
                str(subscription['_id']),
                f"Subscription payment completed: {subscription['currency']} {subscription['amount']}"
            )
            
            return 'OK', 200
        
        elif status in ['failed', 'expired', 'cancelled', 'wrong_amount', 'system_fail', 'cancel', 'fail']:
            # Update subscription status to expired (matching orders pattern)
            Subscription.update_subscription(subscription['_id'], 
                                           status='expired', 
                                           webhook_payload=data)
            print(f"Subscription {subscription['_id']} marked as expired due to status: {status}")
            
            return 'OK', 200
        
        # For other statuses, just log the webhook
        Subscription.update_subscription(subscription['_id'], webhook_payload=data)
        print(f"Subscription {subscription['_id']} webhook logged with status: {status}")
        
        return 'OK', 200
        
    except Exception as e:
        print(f"Error processing subscription webhook: {e}")
        return 'Internal server error', 500

@subscriptions_bp.route('/success')
@login_required
def success():
    """Payment success page"""
    return render_template('merchant/subscriptions/success.html')

@subscriptions_bp.route('/history')
@login_required
@check_ban_status
def history():
    """Show subscription history"""
    user_id = session['user_id']
    
    # Get subscription history
    subscriptions = Subscription.get_subscription_history(user_id)
    
    return render_template('merchant/subscriptions/history.html', 
                         subscriptions=subscriptions)

@subscriptions_bp.route('/api/status')
@login_required
def api_status():
    """API endpoint to get current subscription status"""
    user_id = session['user_id']
    
    active_subscription = Subscription.get_active_subscription(user_id)
    pending_subscription = Subscription.get_pending_subscription(user_id)
    
    response = {
        'has_active': bool(active_subscription),
        'has_pending': bool(pending_subscription),
        'is_paid': bool(active_subscription)
    }
    
    if active_subscription:
        response['active_subscription'] = {
            'id': str(active_subscription['_id']),
            'currency': active_subscription['currency'],
            'amount': active_subscription['amount'],
            'starts_at': active_subscription['starts_at'].isoformat(),
            'ends_at': active_subscription['ends_at'].isoformat(),
            'days_remaining': (active_subscription['ends_at'] - datetime.utcnow()).days
        }
    
    if pending_subscription:
        response['pending_subscription'] = {
            'id': str(pending_subscription['_id']),
            'currency': pending_subscription['currency'],
            'amount': pending_subscription['amount'],
            'payment_link': pending_subscription['payment_link'],
            'expires_at': pending_subscription['expires_at'].isoformat(),
            'minutes_remaining': int((pending_subscription['expires_at'] - datetime.utcnow()).total_seconds() / 60)
        }
    
    return jsonify(response)

@subscriptions_bp.route('/cancel/<subscription_id>', methods=['POST'])
@login_required
@check_ban_status
def cancel_subscription(subscription_id):
    """Cancel a pending subscription"""
    user_id = session['user_id']
    
    # Get subscription
    subscription = Subscription.get_by_id(subscription_id)
    
    if not subscription:
        return jsonify({'error': 'Subscription not found'}), 404
    
    # Check if subscription belongs to current user
    if str(subscription['merchant_id']) != str(user_id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Can only cancel pending subscriptions
    if subscription['status'] != 'pending':
        return jsonify({'error': 'Can only cancel pending subscriptions'}), 400
    
    # Update subscription status
    Subscription.update_subscription(subscription_id, status='expired')
    
    return jsonify({'success': True})

@subscriptions_bp.route('/admin/cleanup', methods=['POST'])
def admin_cleanup():
    """Manual subscription cleanup - admin only"""
    # This route is for admin/cron access only
    # In production, you might want to add API key authentication
    from core.scheduler import run_manual_cleanup
    
    result = run_manual_cleanup()
    return jsonify(result)

# Theme management routes for premium users
@subscriptions_bp.route('/themes')
@login_required
@check_ban_status
def themes():
    """Show theme selection page for premium users"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.dashboard'))
    
    # Check if user has premium status
    if not shop.get('is_paid', False):
        flash('Theme selection is only available for Premium subscribers.', 'warning')
        return redirect(url_for('subscriptions.upgrade'))
    
    # Get current theme and available themes
    current_theme = Shop.get_theme(user_id)
    available_themes = Shop.get_available_themes()
    premium_themes = Shop.get_premium_themes()
    
    context = {
        'shop': shop,
        'current_theme': current_theme,
        'available_themes': available_themes,
        'premium_themes': premium_themes
    }
    
    return render_template('merchant/subscriptions/themes.html', **context)

@subscriptions_bp.route('/set-theme', methods=['POST'])
@login_required
@check_ban_status
def set_theme():
    """Set theme for premium user"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return jsonify({'error': 'Shop not found'}), 404
    
    # Check if user has premium status
    if not shop.get('is_paid', False):
        return jsonify({'error': 'Theme selection is only available for Premium subscribers'}), 403
    
    theme_name = request.form.get('theme')
    if not theme_name:
        return jsonify({'error': 'Theme name is required'}), 400
    
    try:
        Shop.set_theme(user_id, theme_name)
        return jsonify({
            'success': True,
            'message': f'Theme changed to {theme_name}',
            'theme': theme_name
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to change theme: {str(e)}'}), 500

@subscriptions_bp.route('/preview-theme/<theme_name>')
@login_required
@check_ban_status
def preview_theme(theme_name):
    """Preview a theme (available to all users for demonstration)"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.dashboard'))
    
    # Validate theme exists
    if theme_name not in Shop.get_available_themes():
        flash('Invalid theme selected.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    # Render shop with preview theme
    username = shop['owner']['username']
    user = shop
    user_id = str(user['_id'])
    shop_name = user['name']
    
    # Get online status for this merchant
    online_status = Shop.get_online_status(user_id)
    last_online_message = Shop.get_last_online_message(user_id)
    
    # Get products (simplified for preview)
    all_products = user.get('products', [])
    products = []
    
    for product in all_products[:9]:  # Limit to 9 products for preview
        is_visible = product.get('is_visible', True)
        # Fix availability check to include duration pricing products
        is_available = product.get('infinite_stock') or (product.get('stock', 0) > 0) or (product.get('has_duration_pricing') and any(option.get('stock', 0) > 0 for option in product.get('pricing_options', [])))
        if is_visible and is_available:
            if product.get('category_id'):
                for category in user.get('categories', []):
                    if str(category['_id']) == product['category_id']:
                        product['category_name'] = category['name']
                        break
                else:
                    product['category_name'] = 'ALL'
            else:
                product['category_name'] = 'ALL'
            
            # For products with duration pricing, calculate availability and stock info
            if product.get('has_duration_pricing') and product.get('pricing_options'):
                available_options = 0
                total_stock = 0
                for option in product['pricing_options']:
                    option_stock = option.get('stock', 0)
                    if isinstance(option_stock, int):
                        total_stock += option_stock
                        if option_stock > 0:
                            available_options += 1
                product['total_duration_stock'] = total_stock
                product['available_duration_options'] = available_options
            elif not product.get('has_duration_pricing'): # Ensure stock is an int for non-duration products
                 product['stock'] = int(product.get('stock', 0))
            
            products.append(product)
    
    # Get categories
    categories = user.get('categories', [])
    
    # Determine template path
    template_path = f'themes/{theme_name}.html'
    
    # Fallback to classic theme if theme template doesn't exist
    try:
        from flask import current_app
        current_app.jinja_env.get_template(template_path)
    except:
        template_path = 'themes/classic.html'
    
    return render_template(template_path,
                          shop_name=shop_name,
                          username=username,
                          products=products,
                          categories=categories,
                          current_category_name='All Products',
                          search_query='',
                          public_coupons=[],
                          shop_avatar_url=user.get('avatar_url'),
                          shop_description=user.get('description', 'Welcome to our digital marketplace!'),
                          online_status=online_status,
                          last_online_message=last_online_message,
                          is_preview=True,
                          preview_theme_name=theme_name)
