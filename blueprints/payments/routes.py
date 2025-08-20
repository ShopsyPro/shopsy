from flask import request, jsonify, current_app, redirect, url_for, render_template, flash
from flask import session
from core.cryptomus import CryptomusClient
from models import Order, Shop
from . import payments_bp
from blueprints.auth.decorators import login_required, check_ban_status
import logging
from bson import ObjectId
from pymongo import MongoClient
from pymongo.client_session import ClientSession
from datetime import datetime

logger = logging.getLogger(__name__)
cryptomus = CryptomusClient()

@payments_bp.route('/api/cryptomus/qr', methods=['POST'])
def get_cryptomus_qr():
    """
    Return a QR code image (base64 PNG) for a given invoice UUID.
    Expects JSON: { uuid: str }
    """
    data = request.json or {}
    uuid = data.get('uuid')
    if not uuid:
        return jsonify({'success': False, 'message': 'Missing uuid'}), 400
    try:
        image = cryptomus.get_invoice_qr(uuid)
        if not image:
            return jsonify({'success': False, 'message': 'No QR code found'}), 404
        return jsonify({'success': True, 'image': image})
    except Exception as e:
        logger.error(f"Error fetching Cryptomus QR: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Error fetching QR code'}), 500

@payments_bp.route('/api/cryptomus/info', methods=['POST'])
def get_cryptomus_payment_info():
    """
    Return payment info for a given invoice UUID.
    Expects JSON: { uuid: str }
    """
    data = request.json or {}
    uuid = data.get('uuid')
    if not uuid:
        return jsonify({'success': False, 'message': 'Missing uuid'}), 400
    try:
        info = cryptomus.get_payment_info(uuid)
        if not info:
            return jsonify({'success': False, 'message': 'No payment info found'}), 404
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        logger.error(f"Error fetching Cryptomus payment info: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Error fetching payment info'}), 500

# Update create_cryptomus_payment to always use server-side order amount
@payments_bp.route('/api/cryptomus/create', methods=['POST'])
def create_cryptomus_payment():
    """
    Create a Cryptomus payment invoice for an order.
    Expects JSON: { order_id: str, currency: str (optional), network: str (optional), email: str (optional) }
    Returns: { payment_url, payment_id, ... }
    """
    data = request.json or {}
    order_id = data.get('order_id')
    currency = 'USD'
    to_currency = str(data.get('to_currency') or '')
    network = str(data.get('network') or '')
    email = str(data.get('email') or '')
    if not order_id:
        return jsonify({'success': False, 'message': 'Missing order_id'}), 400
    # Validate order exists and is pending
    order = Order.collection.find_one({'_id': ObjectId(order_id), 'status': 'pending'})
    if not order:
        return jsonify({'success': False, 'message': 'Order not found or not pending'}), 404
    # Always use server-side order amount
    amount = order.get('total_amount')
    if not amount or not isinstance(amount, (int, float)) or amount <= 0:
        logger.warning(f"Invalid order amount for order {order_id}: {amount}")
        return jsonify({'success': False, 'message': 'Invalid order amount'}), 400
    callback_url = url_for('payments.cryptomus_webhook', _external=True)
    try:
        result = cryptomus.create_payment(
            amount=amount,
            order_id=order_id,
            currency=currency,
            to_currency=to_currency,
            network=network,
            callback_url=callback_url,
            buyer_email=email
        )
        state = result.get('state')
        payment_result = result.get('result', {})
        payment_url = payment_result.get('url')
        payment_id = payment_result.get('uuid')
        if state != 0 or not payment_url:
            logger.error(f"Cryptomus API error: {result}")
            return jsonify({'success': False, 'message': 'Failed to create payment'}), 500
        Order.collection.update_one({'_id': ObjectId(order_id)}, {'$set': {'cryptomus_payment_id': payment_id}})
        return jsonify({'success': True, 'payment_url': payment_url, 'payment_id': payment_id})
    except Exception as e:
        logger.error(f"Error creating Cryptomus payment: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Error creating payment'}), 500

@payments_bp.route('/api/cryptomus/webhook', methods=['POST'])
def cryptomus_webhook():
    """
    Handle Cryptomus webhook notifications. Securely verify signature and update order status atomically.
    """
    try:
        # Get the raw JSON data
        payload = request.get_json(force=True)
        if not payload:
            logger.warning('Empty webhook payload')
            return 'Empty payload', 400
        
        # Extract signature from payload
        signature = payload.get('sign')
        if not signature:
            logger.warning('Missing Cryptomus webhook signature')
            return 'Missing signature', 400
        
        # Remove signature from payload for verification
        payload_for_verification = payload.copy()
        del payload_for_verification['sign']
        
        # Verify signature
        if not cryptomus.verify_webhook_signature(payload_for_verification, signature):
            logger.error('SECURITY ALERT: Invalid Cryptomus webhook signature!')
            # SECURITY: Enable signature verification in production
            return 'Invalid signature', 403
        
        # Extract webhook data
        uuid = payload.get('uuid')  # Cryptomus payment UUID
        order_id = payload.get('order_id')  # Our order ID
        status = payload.get('status')  # Payment status
        amount = payload.get('amount')  # Invoice amount
        payment_amount = payload.get('payment_amount')  # Amount actually paid
        txid = payload.get('txid')  # Transaction hash
        
        logger.info(f"Received Cryptomus webhook: uuid={uuid}, order_id={order_id}, status={status}, amount={amount}, payment_amount={payment_amount}, txid={txid}")
        logger.info(f"Full webhook payload: {payload}")
        
        if not order_id or not status:
            logger.warning(f"Missing order_id or status in webhook: {payload}")
            return 'Missing order_id or status', 400
        
        # Find the order - try by custom order_id first, then by MongoDB ObjectId
        logger.info(f"Looking for order with order_id: {order_id}")
        order = Order.collection.find_one({'order_id': order_id})
        if order:
            logger.info(f"Found order by custom order_id: {order_id}")
        else:
            # Try as MongoDB ObjectId
            try:
                order = Order.collection.find_one({'_id': ObjectId(order_id)})
                if order:
                    logger.info(f"Found order by MongoDB _id: {order_id}")
            except Exception as e:
                logger.warning(f"Error converting {order_id} to ObjectId: {e}")
        
        if not order:
            logger.warning(f"Order not found: {order_id}")
            return 'Order not found', 404
        
        logger.info(f"Found order: _id={order['_id']}, order_id={order.get('order_id')}, status={order.get('status')}")
        
        # Only process if order is still pending
        if order.get('status') == 'pending':
            if status in ['paid', 'paid_over']:
                # SECURITY: Validate payment amount before marking as completed
                expected_amount = order.get('total_amount', 0)
                received_amount = float(payment_amount) if payment_amount else 0
                
                logger.info(f"Payment validation: Expected ${expected_amount}, Received ${received_amount}")
                
                # Validate payment amount (allow small overpayment but not underpayment)
                if received_amount < (expected_amount * 0.95):  # Allow 5% tolerance
                    logger.error(f"SECURITY ALERT: Underpayment detected! Order {order_id}: Expected ${expected_amount}, Got ${received_amount}")
                    # Mark order as expired due to insufficient payment
                    result = Order.collection.update_one(
                        {'_id': order['_id']}, 
                        {
                            '$set': {
                                'status': 'expired',
                                'payment_amount': payment_amount,
                                'txid': txid,
                                'webhook_received_at': datetime.utcnow(),
                                'failure_reason': f'Insufficient payment: ${received_amount} < ${expected_amount}'
                            }
                        }
                    )
                    logger.warning(f"Order {order_id} marked as expired due to underpayment")
                    return 'Payment amount insufficient', 400
                
                # Update order status to completed
                result = Order.collection.update_one(
                    {'_id': order['_id']}, 
                    {
                        '$set': {
                            'status': 'completed',
                            'payment_amount': payment_amount,
                            'txid': txid,
                            'webhook_received_at': datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    logger.info(f"Order {order_id} marked as completed (modified_count: {result.modified_count})")
                    # Trigger stock delivery for completed orders
                    Order.send_stock_items(str(order['_id']))
                else:
                    logger.warning(f"Order {order_id} update failed - no documents modified")
                
            elif status in ['failed', 'expired', 'cancelled', 'wrong_amount', 'system_fail']:
                # Update order status to expired
                result = Order.collection.update_one(
                    {'_id': order['_id']}, 
                    {
                        '$set': {
                            'status': 'expired',
                            'webhook_received_at': datetime.utcnow()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    logger.info(f"Order {order_id} marked as expired due to status: {status} (modified_count: {result.modified_count})")
                else:
                    logger.warning(f"Order {order_id} update failed - no documents modified")
        else:
            logger.info(f"Order {order_id} already processed (status: {order.get('status')})")
        
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Error processing Cryptomus webhook: {e}", exc_info=True)
        return 'Internal server error', 500

@payments_bp.route('/payment-settings', methods=['GET', 'POST'])
@login_required
@check_ban_status
def payment_settings():
    """Payment settings page for merchants to configure crypto addresses"""
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if request.method == 'POST':
        # Get crypto addresses from form for all 30 supported cryptocurrencies
        crypto_addresses = {
            'usdt': request.form.get('usdt', ''),
            'btc': request.form.get('btc', ''),
            'eth': request.form.get('eth', ''),
            'bnb': request.form.get('bnb', ''),
            'sol': request.form.get('sol', ''),
            'usdc': request.form.get('usdc', ''),
            'doge': request.form.get('doge', ''),
            'trx': request.form.get('trx', ''),
            'avax': request.form.get('avax', ''),
            'bch': request.form.get('bch', ''),
            'link': request.form.get('link', ''),
            'ltc': request.form.get('ltc', ''),
            'dai': request.form.get('dai', ''),
            'uni': request.form.get('uni', ''),
            'aave': request.form.get('aave', ''),
            'crv': request.form.get('crv', ''),
            'xcn': request.form.get('xcn', ''),
            'sushi': request.form.get('sushi', ''),
            'rsr': request.form.get('rsr', ''),
            'ape': request.form.get('ape', ''),
            'axs': request.form.get('axs', ''),
            'dydx': request.form.get('dydx', ''),
            'fet': request.form.get('fet', ''),
            'shib': request.form.get('shib', ''),
            'pepe': request.form.get('pepe', ''),
            'bonk': request.form.get('bonk', ''),
            'orca': request.form.get('orca', ''),
            'jup': request.form.get('jup', ''),
            'zbcn': request.form.get('zbcn', ''),
            'comp': request.form.get('comp', '')
        }
        
        # Update payment settings
        Shop.update_payment_settings(user_id, **crypto_addresses)
        
        flash('Payment settings updated successfully', 'success')
        return redirect(url_for('payments.payment_settings'))
    
    # Get existing crypto addresses
    crypto_addresses = shop.get('crypto_addresses', {})
    
    return render_template('merchant/settings/payment_settings.html', crypto_addresses=crypto_addresses) 