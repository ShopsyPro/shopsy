from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app
from datetime import datetime
from models import Shop, Cart, Order
from . import cart_bp
from bson import ObjectId
import json
import os
import logging
import requests

# SECURITY FIX: Use robust email validation library
try:
    from email_validator import validate_email, EmailNotValidError
    EMAIL_VALIDATOR_AVAILABLE = True
except ImportError:
    EMAIL_VALIDATOR_AVAILABLE = False
    import re

logger = logging.getLogger(__name__)

# Helper function to convert MongoDB objects to JSON
def mongo_to_json(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

ALLOWED_CRYPTOS = [
    'BTC', 'ETH', 'USDT', 'BNB', 'SOL', 'USDC', 'DOGE', 'TRX', 'AVAX', 'BCH', 'LINK', 'LTC', 'DAI', 'UNI', 'AAVE', 'CRV', 'XCN', 'SUSHI', 'RSR', 'APE', 'AXS', 'DYDX', 'FET', 'SHIB', 'PEPE', 'BONK', 'ORCA', 'JUP', 'ZBCN', 'COMP'
]

@cart_bp.route('/<username>/cart')
def view_cart(username):
    # SECURITY FIX: Generate a unique cart session ID if not exists with user validation
    if 'cart_id' not in session:
        session['cart_id'] = os.urandom(24).hex()
        session['cart_user'] = username  # Tie cart to user
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        # Clear cart if user changed
        session['cart_id'] = os.urandom(24).hex()
        session['cart_user'] = username
        if 'applied_coupon' in session:
            session.pop('applied_coupon', None)
    
    # Note: Coupons are now preserved on page load and only cleared when cart is modified
    # This improves user experience by maintaining applied coupons across page refreshes
        
    # Get user for shop information
    shop = Shop.get_by_username(username)
    if not shop:
        return render_template('error/404.html'), 404
    
    # Get cart items
    cart = Cart.get_by_session(session['cart_id'])
    cart_items = [item for item in cart.get('items', []) if item.get('seller_username') == username]
    
    # OPTIMIZATION: Fetch all products in a single query instead of N+1 queries
    product_stocks = {}
    if cart_items:
        # Collect all unique product IDs
        product_ids = list(set(item.get('product_id') for item in cart_items if item.get('product_id')))
        
        # Fetch all products in one query
        products_dict = Shop.get_products_by_ids(shop['_id'], product_ids)
        
        # Process each cart item with the fetched products
        for item in cart_items:
            product_id = item.get('product_id')
            if product_id and product_id in products_dict:
                product = products_dict[product_id]
                
                # Make sure each cart item has category information for coupon calculations
                if product.get('category_id') and not item.get('category_id'):
                    item['category_id'] = product.get('category_id')
                
                # Add category name to cart item if not already present
                if product.get('category_id') and not item.get('category_name'):
                    # Find the category name from shop categories
                    for category in shop.get('categories', []):
                        if str(category['_id']) == product.get('category_id'):
                            item['category_name'] = category['name']
                            break
                    else:
                        item['category_name'] = 'ALL'
                elif not product.get('category_id'):
                    item['category_name'] = 'ALL'
                    
                # Add infinite stock flag to cart item
                item['infinite_stock'] = product.get('infinite_stock', False)
                    
                if item.get('duration') and product.get('has_duration_pricing'):
                    # Find the matching duration option to get its stock
                    for option in product.get('pricing_options', []):
                        if option.get('name') == item.get('duration') and 'stock' in option:
                            product_stocks[product_id] = option['stock']
                            break
                    else:
                        # If no specific duration stock found, fall back to main stock
                        product_stocks[product_id] = product.get('stock', 0)
                else:
                    # Use main product stock if no duration specified
                    product_stocks[product_id] = product.get('stock', 0)
    
    # OPTIMIZATION: Simplified coupon processing
    applied_coupon = None
    coupon_error = None
    discount_amount = 0
    total_amount = sum(item.get('subtotal', 0) for item in cart_items)
    
    if 'applied_coupon' in session and session['applied_coupon'].get('shop_id') == str(shop['_id']):
        coupon_code = session['applied_coupon'].get('code')
        coupon = Shop.get_coupon_by_code(shop['_id'], coupon_code)
        
        if coupon:
            # Check if coupon is valid
            now = datetime.utcnow()
            if coupon.get('expiry_date') and coupon['expiry_date'] < now:
                coupon_error = "This coupon has expired."
                session.pop('applied_coupon', None)
            elif coupon.get('status') != 'Active':
                coupon_error = "This coupon is no longer active."
                session.pop('applied_coupon', None)
            else:
                # Valid coupon, apply discount
                applied_coupon = coupon
                coupon_type = coupon.get('type', 'percentage')
                discount_value = coupon.get('discount_value', coupon.get('discount_percentage', 0))
                max_cap = coupon.get('max_cap')
                min_order_value = coupon.get('min_order_value', 0)
                
                # Add category name to the coupon if it has a category
                if coupon.get('category_id'):
                    for category in shop.get('categories', []):
                        if str(category['_id']) == coupon['category_id']:
                            applied_coupon['category_name'] = category['name']
                            break
                
                # OPTIMIZATION: Simplified discount calculation
                if coupon.get('category_id'):
                    # Apply discount only to items in the specified category
                    category_subtotal = 0
                    for item in cart_items:
                        product_id = item.get('product_id')
                        if product_id and product_id in products_dict:
                            product = products_dict[product_id]
                            if product and product.get('category_id') == coupon['category_id']:
                                category_subtotal += item.get('subtotal', 0)
                    
                    # Calculate discount based on coupon type
                    if coupon_type == 'fixed':
                        if min_order_value > 0 and category_subtotal < min_order_value:
                            discount_amount = 0  # Minimum order value not met
                        else:
                            discount_amount = min(float(discount_value), category_subtotal)
                    else:  # percentage
                        discount_amount = category_subtotal * float(discount_value) / 100
                        if max_cap and discount_amount > max_cap:
                            discount_amount = max_cap
                else:
                    # Apply discount to all items
                    if coupon_type == 'fixed':
                        if min_order_value > 0 and total_amount < min_order_value:
                            discount_amount = 0  # Minimum order value not met
                        else:
                            discount_amount = min(float(discount_value), total_amount)
                    else:  # percentage
                        discount_amount = total_amount * float(discount_value) / 100
                        if max_cap and discount_amount > max_cap:
                            discount_amount = max_cap
                
                # Round discount amount to 2 decimal places for consistency
                discount_amount = round(discount_amount, 2)
                
                # Update total amount after discount
                total_amount -= discount_amount
    
    return render_template('shop/cart.html', 
                           username=username, 
                           shop_name=shop.get('name', 'Shop'),
                           cart_items=cart_items,
                           product_stocks=product_stocks,
                           total_items=sum(item.get('quantity', 0) for item in cart_items),
                           total_amount=total_amount,
                           applied_coupon=applied_coupon,
                           coupon_error=coupon_error,
                           discount_amount=discount_amount)

@cart_bp.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    username = data.get('username')
    duration = data.get('duration')
    # SECURITY FIX: Remove client-provided price - always use server-side pricing
    # price = data.get('price')  # REMOVED - Never trust client prices
    
    if not product_id or not username:
        return jsonify({
            'success': False,
            'message': 'Product ID and username are required'
        }), 400
    
    # OPTIMIZATION: Get shop_id from username once
    shop = Shop.get_by_username(username)
    if not shop:
        return jsonify({
            'success': False,
            'message': 'Shop not found'
        }), 404
        
    shop_id = str(shop['_id'])
    
    # SECURITY FIX: Generate unique cart session ID with user validation
    if 'cart_id' not in session:
        session['cart_id'] = os.urandom(24).hex()
        session['cart_user'] = username  # Tie cart to user
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        # Clear cart if user changed
        session['cart_id'] = os.urandom(24).hex()
        session['cart_user'] = username
        if 'applied_coupon' in session:
            session.pop('applied_coupon', None)
    
    # Clear any applied coupons when cart is modified
    if 'applied_coupon' in session:
        session.pop('applied_coupon', None)
    
    try:
        # SECURITY FIX: Use optimized add_item method without client price
        cart = Cart.add_item(
            session['cart_id'], 
            shop_id,
            product_id, 
            quantity, 
            duration=duration
            # price parameter removed - always use server-side pricing
        )
        
        # OPTIMIZATION: Calculate shop-specific cart count efficiently
        shop_total_items = 0
        for item in cart.get('items', []):
            if item.get('seller_username') == username:
                shop_total_items += item.get('quantity', 0)
        
        return jsonify({
            'success': True,
            'message': 'Item added to cart',
            'cart_total_items': shop_total_items
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@cart_bp.route('/api/cart/update', methods=['POST'])
def update_cart_item():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    duration = data.get('duration')
    username = data.get('username')  # SECURITY FIX: Add username validation
    
    if not product_id or not username:
        return jsonify({
            'success': False,
            'message': 'Product ID and username are required'
        }), 400
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        return jsonify({
            'success': False,
            'message': 'Cart session mismatch'
        }), 400
    
    if 'cart_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Cart not found'
        }), 404
    
    # Clear any applied coupons when cart is modified
    if 'applied_coupon' in session:
        session.pop('applied_coupon', None)
    
    try:
        Cart.update_item(session['cart_id'], product_id, quantity, duration=duration)
        return jsonify({
            'success': True,
            'message': 'Cart updated successfully'
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400
    
@cart_bp.route('/api/cart/item-quantity/<username>/<product_id>', methods=['GET'])
def get_item_quantity(username, product_id):
    """Get current quantity of an item in cart"""
    if 'cart_id' not in session:
        return jsonify({'success': True, 'quantity': 0})
    
    # Security validation
    if session.get('cart_user') != username:
        return jsonify({'success': True, 'quantity': 0})
    
    duration = request.args.get('duration')
    
    cart = Cart.get_by_session(session['cart_id'])
    cart_items = [item for item in cart.get('items', []) if item.get('seller_username') == username]
    
    for item in cart_items:
        if (item.get('product_id') == product_id and 
            item.get('duration') == duration):
            return jsonify({'success': True, 'quantity': item.get('quantity', 0)})
    
    return jsonify({'success': True, 'quantity': 0})


@cart_bp.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    product_id = data.get('product_id')
    duration = data.get('duration')
    username = data.get('username')  # SECURITY FIX: Add username validation
    
    if not product_id or not username:
        return jsonify({
            'success': False,
            'message': 'Product ID and username are required'
        }), 400
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        return jsonify({
            'success': False,
            'message': 'Cart session mismatch'
        }), 400
    
    if 'cart_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Cart not found'
        }), 404
    
    # Clear any applied coupons when cart is modified
    if 'applied_coupon' in session:
        session.pop('applied_coupon', None)
    
    try:
        Cart.remove_item(session['cart_id'], product_id, duration=duration)
        return jsonify({
            'success': True,
            'message': 'Item removed from cart successfully'
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@cart_bp.route('/api/cart', methods=['GET'])
def get_cart():
    if 'cart_id' not in session:
        session['cart_id'] = os.urandom(24).hex()
        
    cart = Cart.get_by_session(session['cart_id'])
    # Convert MongoDB ObjectIds to strings for JSON serialization
    serializable_cart = json.loads(json.dumps(cart, default=mongo_to_json))
    return jsonify(serializable_cart)

@cart_bp.route('/api/cart/<username>', methods=['GET'])
def get_cart_for_shop(username):
    """Get cart data filtered for a specific shop"""
    if 'cart_id' not in session:
        session['cart_id'] = os.urandom(24).hex()
        
    cart = Cart.get_by_session(session['cart_id'])
    
    # Filter items for this shop only
    shop_items = [item for item in cart.get('items', []) if item.get('seller_username') == username]
    shop_total_items = sum(item.get('quantity', 0) for item in shop_items)
    shop_total_amount = sum(item.get('subtotal', 0) for item in shop_items)
    
    # Create shop-specific cart data
    shop_cart = {
        'session_id': cart.get('session_id'),
        'items': shop_items,
        'total_items': shop_total_items,
        'total_amount': shop_total_amount
    }
    
    # Convert MongoDB ObjectIds to strings for JSON serialization
    serializable_cart = json.loads(json.dumps(shop_cart, default=mongo_to_json))
    return jsonify(serializable_cart)

@cart_bp.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    username = data.get('username')  # SECURITY FIX: Add username validation
    
    if not username:
        return jsonify({
            'success': False,
            'message': 'Username is required'
        }), 400
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        return jsonify({
            'success': False,
            'message': 'Cart session mismatch'
        }), 400
    
    if 'cart_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Cart not found'
        }), 404
    
    # Clear cart items for this specific shop only
    cart = Cart.get_by_session(session['cart_id'])
    if cart:
        # Filter out items from other shops
        remaining_items = [item for item in cart.get('items', []) if item.get('seller_username') != username]
        
        if remaining_items:
            # Update cart with remaining items from other shops
            total_items = sum(item.get('quantity', 0) for item in remaining_items)
            total_amount = sum(item.get('subtotal', 0) for item in remaining_items)
            
            Cart.collection.update_one(
                {"session_id": session['cart_id']},
                {
                    "$set": {
                        "items": remaining_items,
                        "total_items": total_items,
                        "total_amount": total_amount,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        else:
            # Clear entire cart if no items from other shops
            Cart.clear(session['cart_id'])
    
    # Clear applied coupon
    if 'applied_coupon' in session:
        session.pop('applied_coupon', None)
        
    return jsonify({
        'success': True,
        'message': 'Cart cleared successfully'
    })

@cart_bp.route('/api/cart/apply-coupon', methods=['POST'])
def apply_coupon():
    data = request.json
    logger.info(f"Apply coupon request data: {data}")
    
    if not data:
        logger.warning("Apply coupon: No request data")
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    coupon_code = data.get('code', '').strip().upper()
    username = data.get('username')
    
    logger.info(f"Apply coupon: code='{coupon_code}', username='{username}'")
    
    if not coupon_code or not username:
        logger.warning(f"Apply coupon: Missing required fields - code: {bool(coupon_code)}, username: {bool(username)}")
        return jsonify({
            'success': False,
            'message': 'Missing coupon code or username'
        }), 400
    
    # SECURITY FIX: Validate cart belongs to current user
    logger.info(f"Apply coupon: Cart session validation - cart_user: {session.get('cart_user')}, username: {username}")
    if session.get('cart_user') != username:
        logger.warning(f"Apply coupon: Cart session mismatch - cart_user: {session.get('cart_user')}, username: {username}")
        return jsonify({
            'success': False,
            'message': 'Cart session mismatch'
        }), 400
    
    # Get shop by username
    shop = Shop.get_by_username(username)
    logger.info(f"Apply coupon: Shop lookup for username '{username}' - found: {shop is not None}")
    if not shop:
        logger.warning(f"Apply coupon: Shop not found for username '{username}'")
        return jsonify({
            'success': False,
            'message': 'Shop not found'
        }), 404
    
    # Get cart
    if 'cart_id' not in session:
        logger.warning(f"Apply coupon: No cart_id in session")
        return jsonify({
            'success': False,
            'message': 'Cart not found'
        }), 404
    
    cart = Cart.get_by_session(session['cart_id'])
    logger.info(f"Apply coupon: Cart lookup - cart_id: {session['cart_id']}, cart found: {cart is not None}")
    
    cart_items = [item for item in cart.get('items', []) if item.get('seller_username') == username]
    logger.info(f"Apply coupon: Cart items for username '{username}' - count: {len(cart_items)}")
    
    if not cart_items:
        logger.warning(f"Apply coupon: No cart items found for username '{username}'")
        return jsonify({
            'success': False,
            'message': 'Your cart is empty'
        }), 400
    
    # SECURITY FIX: Look up the coupon with shop verification
    logger.info(f"Apply coupon: Looking for coupon code '{coupon_code}' in shop {shop['_id']}")
    coupon = Shop.get_coupon_by_code(shop['_id'], coupon_code)
    logger.info(f"Apply coupon: Coupon lookup result - found: {coupon is not None}")
    if not coupon:
        logger.warning(f"Apply coupon: Coupon code '{coupon_code}' not found in shop {shop['_id']}")
        return jsonify({
            'success': False,
            'message': 'Invalid coupon code'
        }), 400
    
    # SECURITY FIX: Verify coupon belongs to the correct shop
    # Note: Coupons are stored directly in the shop's coupons array, so they don't have a shop_id field
    # The security is already ensured by looking up the coupon within the specific shop
    logger.info(f"Apply coupon: Coupon validation passed - coupon found in shop {shop['_id']}")
    
    # Check if coupon is valid
    now = datetime.utcnow()
    if coupon.get('expiry_date') and coupon['expiry_date'] < now:
        return jsonify({
            'success': False,
            'message': 'This coupon has expired'
        }), 400
    
    if coupon.get('status') != 'Active':
        return jsonify({
            'success': False,
            'message': 'This coupon is not active'
        }), 400
    
    # Store the coupon in the session
    session['applied_coupon'] = {
        'code': coupon['code'],
        'shop_id': str(shop['_id']),
    }
    
    # Prepare coupon data for client-side
    coupon_data = {
        'code': coupon['code'],
        'type': coupon.get('type', 'percentage'),
        'discount_value': coupon.get('discount_value', coupon.get('discount_percentage', 0)),
        'discount_percentage': coupon.get('discount_percentage', 0),
        'max_cap': coupon.get('max_cap'),
        'min_order_value': coupon.get('min_order_value'),
        'category_id': coupon.get('category_id'),
        'category_name': coupon.get('category_name')
    }
    
    return jsonify({
        'success': True,
        'message': 'Coupon applied successfully',
        'coupon': coupon_data
    })

@cart_bp.route('/api/cart/remove-coupon', methods=['POST'])
def remove_coupon():
    if 'applied_coupon' in session:
        session.pop('applied_coupon', None)
        
    return jsonify({
        'success': True,
        'message': 'Coupon removed successfully'
    })

@cart_bp.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request data'
        }), 400
    
    username = data.get('username')
    customer_email = data.get('email', '').lower().strip() if data.get('email') else None
    
    # SECURITY FIX: Add server-side email validation
    if customer_email:
        if EMAIL_VALIDATOR_AVAILABLE:
            try:
                validate_email(customer_email)
            except EmailNotValidError as e:
                return jsonify({
                    'success': False,
                    'message': f'Please enter a valid email address: {str(e)}'
                }), 400
        else:
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_regex, customer_email):
                return jsonify({
                    'success': False,
                    'message': 'Please enter a valid email address'
                }), 400
    
    if not username:
        return jsonify({
            'success': False,
            'message': 'Missing seller username'
        }), 400
    
    # SECURITY FIX: Validate cart belongs to current user
    if session.get('cart_user') != username:
        return jsonify({
            'success': False,
            'message': 'Cart session mismatch'
        }), 400
    
    # Get shop
    shop = Shop.get_by_username(username)
    if not shop:
        return jsonify({
            'success': False,
            'message': 'Shop not found'
        }), 404
    
    shop_id = str(shop['_id'])
    
    # Get cart
    if 'cart_id' not in session:
        return jsonify({
            'success': False,
            'message': 'Cart not found or empty'
        }), 404
    
    cart = Cart.get_by_session(session['cart_id'])
    cart_items = [item for item in cart.get('items', []) if item.get('seller_username') == username]
    
    if not cart_items:
        return jsonify({
            'success': False,
            'message': 'Your cart is empty'
        }), 400
    
    # SECURITY FIX: Comprehensive stock validation before checkout
    validated_items = []
    total_amount = 0
    
    # Get all products for validation
    product_ids = list(set(item.get('product_id') for item in cart_items if item.get('product_id')))
    products_dict = Shop.get_products_by_ids(shop_id, product_ids)
    
    for item in cart_items:
        product_id = item.get('product_id')
        quantity = item.get('quantity', 0)
        duration = item.get('duration')
        
        if not product_id or quantity <= 0:
            continue
            
        product = products_dict.get(product_id)
        if not product:
            return jsonify({
                'success': False,
                'message': f'Product {product_id} not found'
            }), 400
        
        # Check if product is still available
        is_visible = product.get('is_visible', True)
        if not is_visible:
            return jsonify({
                'success': False,
                'message': f'Product {product.get("name")} is no longer available'
            }), 400
        
        # Check stock availability
        available_stock = product.get('stock', 0)
        if product.get('has_duration_pricing') and duration:
            for option in product.get('pricing_options', []):
                if option.get('name') == duration:
                    available_stock = option.get('stock', 0)
                    break
        
        # For infinite stock products, always allow
        if not product.get('infinite_stock', False) and quantity > available_stock:
            return jsonify({
                'success': False,
                'message': f'Not enough stock for {product.get("name")}. Available: {available_stock}, Requested: {quantity}'
            }), 400
        
        # Recalculate price to ensure it's correct (server-side pricing)
        item_price = float(product.get('price', 0))
        if product.get('has_duration_pricing') and duration:
            for option in product.get('pricing_options', []):
                if option.get('name') == duration:
                    item_price = float(option.get('price', item_price))
                    break
        
        # Update item with validated data
        item['price'] = item_price
        item['subtotal'] = item_price * quantity
        validated_items.append(item)
        total_amount += item['subtotal']
    
    if not validated_items:
        return jsonify({
            'success': False,
            'message': 'No valid items in cart'
        }), 400
    
    # SECURITY FIX: Coupon validation with shop verification
    applied_coupon = None
    if 'applied_coupon' in session and session['applied_coupon'].get('shop_id') == shop_id:
        coupon_code = session['applied_coupon'].get('code')
        coupon = Shop.get_coupon_by_code(shop_id, coupon_code)
        
        # SECURITY FIX: Verify coupon belongs to correct shop
        if coupon and coupon.get('shop_id') == shop_id:
            # Check if coupon is still valid
            now = datetime.utcnow()
            if (coupon.get('status') == 'Active' and 
                (not coupon.get('expiry_date') or coupon['expiry_date'] >= now)):
                applied_coupon = coupon
                # Calculate discount amount
                discount_amount = 0
                coupon_type = coupon.get('type', 'percentage')
                discount_value = coupon.get('discount_value', coupon.get('discount_percentage', 0))
                
                if coupon_type == 'percentage':
                    discount_amount = total_amount * float(discount_value) / 100
                    max_cap = coupon.get('max_cap')
                    if max_cap and discount_amount > max_cap:
                        discount_amount = max_cap
                else:  # fixed
                    discount_amount = min(float(discount_value), total_amount)
                
                # Round discount amount to 2 decimal places for consistency
                discount_amount = round(discount_amount, 2)
                total_amount -= discount_amount
    
    try:
        # Determine order status based on total amount
        if total_amount <= 0:
            # For $0 orders, process directly as completed
            order_status = 'completed'
        else:
            # For paid orders, start as pending
            order_status = 'pending'
            
        order = Order.create(
            shop_id=shop_id,
            session_id=session['cart_id'],
            items=validated_items,  # Use validated items
            total_amount=total_amount,
            customer_email=customer_email,
            coupon=applied_coupon,
            status=order_status
        )
        
        # Clear the applied coupon from the session
        if 'applied_coupon' in session:
            session.pop('applied_coupon', None)
        
        # Clear the cart after successful order creation
        Cart.clear(session['cart_id'])
        
        # Handle $0 orders directly
        if total_amount <= 0:
            return jsonify({
                'success': True,
                'message': 'Order completed successfully!',
                'order_id': str(order['_id']),
                'payment_url': None
            })
        
        # For paid orders, proceed with Cryptomus payment
        currency = data.get('currency', 'USDT')
        if currency not in ALLOWED_CRYPTOS:
            return jsonify({'success': False, 'message': 'Invalid or unsupported cryptocurrency selected.'}), 400
        
        # After order is created, call Cryptomus payment endpoint
        try:
            payments_url = url_for('payments.create_cryptomus_payment', _external=True)
            payload = {
                'order_id': str(order['_id']),
                'currency': 'USD',
                'to_currency': currency,
                'email': customer_email
            }
            resp = requests.post(payments_url, json=payload, timeout=10)
            resp.raise_for_status()
            payment_data = resp.json()
            if not payment_data.get('success'):
                return jsonify({'success': False, 'message': 'Failed to create payment'}), 500
            payment_url = payment_data.get('payment_url')
            return jsonify({
                'success': True,
                'message': 'Order created, redirecting to Cryptomus payment',
                'order_id': str(order['_id']),
                'payment_url': payment_url
            })
        except Exception as e:
            logger.error(f"Error creating Cryptomus payment: {e}", exc_info=True)
            return jsonify({'success': False, 'message': 'Error creating payment'}), 500
    except Exception as e:
        logger.error(f"Error processing checkout for user {username} with email {customer_email}: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An error occurred while processing your order.'
        }), 500 