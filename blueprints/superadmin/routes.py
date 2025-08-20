import os
import time
import hashlib
import hmac
import threading
from datetime import datetime, timedelta
from flask import (
    render_template, request, session, redirect, url_for, 
    flash, jsonify, current_app, abort
)
from . import superadmin_bp
from .decorators import (
    super_admin_required, rate_limit_super_admin, 
    SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD_HASH,
    SUPER_ADMIN_SECRET_KEY, generate_super_admin_token,
    verify_super_admin_token, get_client_ip, is_ip_allowed
)
from werkzeug.security import check_password_hash
from models.shop import Shop
from models.order import Order
from models.customer import CustomerOTP, CustomerOrderTracker

# Background task for cleanup
def background_cleanup_task():
    """Background task to handle expired orders and cache warming"""
    def cleanup():
        try:
            # Handle expired pending orders
            ninety_minutes_ago = datetime.utcnow() - timedelta(minutes=90)
            expired_count = Order.collection.update_many(
                {
                    "status": "pending",
                    "created_at": {"$lt": ninety_minutes_ago}
                },
                {
                    "$set": {
                        "status": "expired",
                        "updated_at": datetime.utcnow()
                    }
                }
            ).modified_count
            
            if expired_count > 0:
                current_app.logger.info(f"Background task: Updated {expired_count} expired orders")
                
                # Invalidate relevant cache
                from .stats_cache import stats_cache
                stats_cache.invalidate_cache(['platform_stats'])
        
        except Exception as e:
            if current_app:
                current_app.logger.error(f"Background cleanup error: {e}")
    
    return cleanup

# Start background cleanup every 5 minutes
def start_background_tasks():
    """Start background tasks"""
    def run_periodic_cleanup():
        while True:
            time.sleep(300)  # 5 minutes
            if current_app:
                with current_app.app_context():
                    cleanup_func = background_cleanup_task()
                    cleanup_func()
    
    cleanup_thread = threading.Thread(target=run_periodic_cleanup, daemon=True)
    cleanup_thread.start()

# Initialize background tasks when app starts
def init_background_tasks(app):
    """Initialize background tasks when app starts"""
    with app.app_context():
        start_background_tasks()

@superadmin_bp.route('/login', methods=['GET', 'POST'])
@rate_limit_super_admin
def login():
    """Super admin login page"""
    # Check IP whitelist
    client_ip = get_client_ip()
    if not is_ip_allowed(client_ip):
        # Log the attempt but don't expose super admin existence
        current_app.logger.warning(f"Unauthorized access attempt from IP: {client_ip}")
        # Return 404 instead of 403 to hide super admin existence
        abort(404)
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Verify credentials
        if (username == SUPER_ADMIN_USERNAME and 
            check_password_hash(SUPER_ADMIN_PASSWORD_HASH, password)):
            
            # Generate secure session
            timestamp = int(time.time())
            token = generate_super_admin_token(username, timestamp)
            
            # Set session data
            session['super_admin_authenticated'] = True
            session['super_admin_username'] = username
            session['super_admin_token'] = token
            session['super_admin_timestamp'] = timestamp
            session['super_admin_ip'] = client_ip
            
            # Log successful login
            current_app.logger.info(f"Super admin login successful: {username} from IP: {client_ip}")
            
            flash('Super Admin login successful!', 'success')
            return redirect(url_for('superadmin.dashboard'))
        else:
            current_app.logger.warning(f"Failed super admin login attempt from IP: {client_ip}")
            flash('Invalid credentials', 'error')
    
    return render_template('superadmin/login.html')

@superadmin_bp.route('/logout')
def logout():
    """Super admin logout"""
    if session.get('super_admin_authenticated'):
        current_app.logger.info(f"Super admin logout: {session.get('super_admin_username')}")
        session.clear()
        flash('Logged out successfully', 'success')
    
    return redirect(url_for('superadmin.login'))

@superadmin_bp.route('/')
@super_admin_required
@rate_limit_super_admin
def dashboard():
    """Super admin main dashboard"""
    return redirect(url_for('superadmin.overview'))

@superadmin_bp.route('/overview')
@super_admin_required
@rate_limit_super_admin
def overview():
    """Super admin overview dashboard - OPTIMIZED"""
    from .stats_cache import stats_cache
    
    # Get all stats from cache
    platform_stats = stats_cache.get_platform_stats()
    top_merchants = stats_cache.get_top_merchants(10)
    recent_orders = stats_cache.get_recent_orders(10)
    
    # Get recent shops with minimal data
    recent_shops = list(Shop.collection.find(
        {}, 
        {"name": 1, "owner.username": 1, "created_at": 1}
    ).sort("created_at", -1).limit(5))
    
    return render_template('superadmin/overview.html',
                         total_shops=platform_stats['total_shops'],
                         total_orders=platform_stats['total_orders'],
                         total_customers=platform_stats['total_customers'],
                         total_revenue=platform_stats['total_revenue'],
                         completed_orders=platform_stats['completed_orders'],
                         recent_orders=recent_orders,
                         recent_shops=recent_shops,
                         top_merchants=top_merchants,
                         new_shops_count=platform_stats['new_shops_30d'],
                         new_orders_count=platform_stats['new_orders_24h'],
                         recent_revenue=platform_stats['recent_revenue'])

@superadmin_bp.route('/merchants')
@super_admin_required
@rate_limit_super_admin
def merchants():
    """View all merchants with detailed information - OPTIMIZED"""
    from .stats_cache import stats_cache
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    skip = (page - 1) * per_page
    
    # Get shops with only needed fields for listing
    shops = list(Shop.collection.find(
        {},
        {
            "name": 1, "owner": 1, "merchant_code": 1, "avatar_url": 1,
            "created_at": 1, "banned": 1
        }
    ).sort("created_at", -1).skip(skip).limit(per_page))
    
    total_shops = Shop.collection.estimated_document_count()  # Much faster than count_documents
    
    if shops:
        # Get shop IDs for batch processing
        shop_ids = [shop['_id'] for shop in shops]
        
        # Get batch stats for all shops at once
        batch_stats = stats_cache.get_merchant_batch_stats(shop_ids)
        
        # Add stats to shops efficiently
        for shop in shops:
            shop_id_str = str(shop['_id'])
            stats = batch_stats.get(shop_id_str, {})
            
            shop['order_count'] = stats.get('order_count', 0)
            shop['total_revenue'] = stats.get('total_revenue', 0)
            
            # Account status is handled in template
    
    total_pages = (total_shops + per_page - 1) // per_page
    
    return render_template('superadmin/merchants.html',
                         shops=shops,
                         page=page,
                         total_pages=total_pages,
                         total_shops=total_shops)

@superadmin_bp.route('/merchant/<shop_id>')
@super_admin_required
@rate_limit_super_admin
def merchant_detail(shop_id):
    """View detailed information for a specific merchant"""
    shop = Shop.get_by_id(shop_id)
    if not shop:
        flash('Merchant not found', 'error')
        return redirect(url_for('superadmin.merchants'))
    
    # Get merchant statistics
    orders = Order.get_by_shop(shop_id)
    total_orders = len(orders)
    
    # Calculate revenue
    completed_orders = [order for order in orders if order.get('status') == 'completed']
    total_revenue = sum(order.get('total_amount', 0) for order in completed_orders)
    
    # Get recent orders
    recent_orders = orders[:10]
    
    # Get products count
    products_count = len(shop.get('products', []))
    
    # Get categories count
    categories_count = len(shop.get('categories', []))
    
    # Get coupons count
    coupons_count = len(shop.get('coupons', []))
    
    # Get recent activities
    recent_activities = Shop.get_recent_activities(shop_id, hours=24)
    
    # Get online status
    online_status = Shop.get_online_status(shop_id)
    last_online_data = Shop.get_last_online_data(shop_id)
    
    return render_template('superadmin/merchant_detail.html',
                         shop=shop,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         completed_orders=len(completed_orders),
                         recent_orders=recent_orders,
                         products_count=products_count,
                         categories_count=categories_count,
                         coupons_count=coupons_count,
                         recent_activities=recent_activities,
                         online_status=online_status,
                         last_online_data=last_online_data)

@superadmin_bp.route('/merchant/<shop_id>/delete', methods=['POST'])
@super_admin_required
@rate_limit_super_admin
def delete_shop(shop_id):
    """Delete a shop with superuser password confirmation"""
    try:
        # Get superuser password from form
        superuser_password = request.form.get('superuser_password')
        
        if not superuser_password:
            flash('Superuser password is required for this action', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Verify superuser password
        if not check_password_hash(SUPER_ADMIN_PASSWORD_HASH, superuser_password):
            flash('Invalid superuser password', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Get shop details before deletion
        shop = Shop.get_by_id(shop_id)
        if not shop:
            flash('Shop not found', 'error')
            return redirect(url_for('superadmin.merchants'))
        
        shop_name = shop.get('name', 'Unknown Shop')
        shop_username = shop.get('owner', {}).get('username', 'Unknown')
        shop_email = shop.get('owner', {}).get('email', 'Unknown')
        
        # Convert shop_id to ObjectId for database operations
        from bson import ObjectId
        shop_object_id = ObjectId(shop_id)
        
        # Log the deletion attempt
        current_app.logger.info(f"Attempting to delete shop: {shop_name} (@{shop_username}) with ID: {shop_id}")
        
        # Delete all orders for this shop
        orders_deleted = Order.collection.delete_many({"shop_id": shop_object_id})
        current_app.logger.info(f"Deleted {orders_deleted.deleted_count} orders for shop {shop_id}")
        
        # Delete the shop
        result = Shop.collection.delete_one({"_id": shop_object_id})
        current_app.logger.info(f"Shop deletion result: {result.deleted_count} shops deleted")
        
        if result.deleted_count > 0:
            # Invalidate cache
            from .stats_cache import stats_cache
            stats_cache.invalidate_cache(['platform_stats', 'top_merchants_10'])
            
            # Log the deletion
            current_app.logger.warning(
                f"Super admin deleted shop: {shop_name} (@{shop_username}, {shop_email}, ID: {shop_id}) "
                f"with {orders_deleted.deleted_count} orders"
            )
            
            flash(f'Shop "{shop_name}" (@{shop_username}) deleted successfully. {orders_deleted.deleted_count} orders also deleted.', 'success')
        else:
            flash('Shop not found or already deleted', 'error')
        
        return redirect(url_for('superadmin.merchants'))
        
    except Exception as e:
        current_app.logger.error(f"Error deleting shop {shop_id}: {e}")
        flash('Error deleting shop', 'error')
        return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))

@superadmin_bp.route('/merchant/<shop_id>/ban', methods=['POST'])
@super_admin_required
@rate_limit_super_admin
def ban_shop(shop_id):
    """Ban a shop with reason"""
    try:
        # Get superuser password from form
        superuser_password = request.form.get('superuser_password')
        ban_reason = request.form.get('ban_reason', '').strip()
        
        if not superuser_password:
            flash('Superuser password is required for this action', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        if not ban_reason:
            flash('Ban reason is required', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Verify superuser password
        if not check_password_hash(SUPER_ADMIN_PASSWORD_HASH, superuser_password):
            flash('Invalid superuser password', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Get shop details before banning
        shop = Shop.get_by_id(shop_id)
        if not shop:
            flash('Shop not found', 'error')
            return redirect(url_for('superadmin.merchants'))
        
        # Check if already banned
        if shop.get('banned'):
            flash('Shop is already banned', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        shop_name = shop.get('name', 'Unknown Shop')
        shop_username = shop.get('owner', {}).get('username', 'Unknown')
        
        # Ban the shop
        if Shop.ban_shop(shop_id, ban_reason, "superadmin"):
            # Invalidate cache
            from .stats_cache import stats_cache
            stats_cache.invalidate_cache(['platform_stats', 'top_merchants_10'])
            
            # Log the ban action
            current_app.logger.warning(
                f"Super admin banned shop: {shop_name} (@{shop_username}, ID: {shop_id}). Reason: {ban_reason}"
            )
            
            flash(f'Shop "{shop_name}" (@{shop_username}) has been banned. Reason: {ban_reason}', 'success')
        else:
            flash('Failed to ban shop', 'error')
        
        return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
    except Exception as e:
        current_app.logger.error(f"Error banning shop {shop_id}: {e}")
        flash('Error banning shop', 'error')
        return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))

@superadmin_bp.route('/merchant/<shop_id>/unban', methods=['POST'])
@super_admin_required
@rate_limit_super_admin
def unban_shop(shop_id):
    """Unban a shop"""
    try:
        # Get superuser password from form
        superuser_password = request.form.get('superuser_password')
        
        if not superuser_password:
            flash('Superuser password is required for this action', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Verify superuser password
        if not check_password_hash(SUPER_ADMIN_PASSWORD_HASH, superuser_password):
            flash('Invalid superuser password', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        # Get shop details before unbanning
        shop = Shop.get_by_id(shop_id)
        if not shop:
            flash('Shop not found', 'error')
            return redirect(url_for('superadmin.merchants'))
        
        # Check if not banned
        if not shop.get('banned'):
            flash('Shop is not banned', 'error')
            return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
        shop_name = shop.get('name', 'Unknown Shop')
        shop_username = shop.get('owner', {}).get('username', 'Unknown')
        
        # Unban the shop
        if Shop.unban_shop(shop_id, "superadmin"):
            # Invalidate cache
            from .stats_cache import stats_cache
            stats_cache.invalidate_cache(['platform_stats', 'top_merchants_10'])
            
            # Log the unban action
            current_app.logger.info(
                f"Super admin unbanned shop: {shop_name} (@{shop_username}, ID: {shop_id})"
            )
            
            flash(f'Shop "{shop_name}" (@{shop_username}) has been unbanned successfully', 'success')
        else:
            flash('Failed to unban shop', 'error')
        
        return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))
        
    except Exception as e:
        current_app.logger.error(f"Error unbanning shop {shop_id}: {e}")
        flash('Error unbanning shop', 'error')
        return redirect(url_for('superadmin.merchant_detail', shop_id=shop_id))

@superadmin_bp.route('/banned')
@super_admin_required
@rate_limit_super_admin
def banned_merchants():
    """View all banned merchants"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    skip = (page - 1) * per_page
    
    # Get banned shops
    banned_shops = list(Shop.collection.find({"banned": True}).sort("banned_at", -1).skip(skip).limit(per_page))
    total_banned = Shop.collection.count_documents({"banned": True})
    total_pages = (total_banned + per_page - 1) // per_page
    
    # Get order counts and revenue for banned shops
    for shop in banned_shops:
        shop_id = str(shop['_id'])
        
        # Get order count and revenue for this shop
        order_count = Order.collection.count_documents({"shop_id": shop['_id']})
        
        # Get revenue for this shop
        revenue_pipeline = [
            {"$match": {"shop_id": shop['_id'], "status": "completed"}},
            {"$group": {"_id": None, "total_revenue": {"$sum": "$total_amount"}}}
        ]
        revenue_stats = list(Order.collection.aggregate(revenue_pipeline))
        total_revenue = revenue_stats[0]['total_revenue'] if revenue_stats else 0
        
        shop['order_count'] = order_count
        shop['total_revenue'] = total_revenue
    
    return render_template('superadmin/banned_merchants.html',
                         shops=banned_shops,
                         page=page,
                         total_pages=total_pages,
                         total_banned=total_banned)

@superadmin_bp.route('/analytics')
@super_admin_required
@rate_limit_super_admin
def analytics():
    """Platform analytics and insights"""
    # Get time range from request
    days = request.args.get('days', 30, type=int)
    
    # Platform revenue over time
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    revenue_pipeline = [
        {"$match": {
            "status": "completed",
            "created_at": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": {
                "year": {"$year": "$created_at"},
                "month": {"$month": "$created_at"},
                "day": {"$dayOfMonth": "$created_at"}
            },
            "total_revenue": {"$sum": "$total_amount"},
            "order_count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    revenue_data = list(Order.collection.aggregate(revenue_pipeline))
    
    # New shops over time
    shops_pipeline = [
        {"$match": {"created_at": {"$gte": start_date, "$lte": end_date}}},
        {"$group": {
            "_id": {
                "year": {"$year": "$created_at"},
                "month": {"$month": "$created_at"},
                "day": {"$dayOfMonth": "$created_at"}
            },
            "shop_count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    shops_data = list(Shop.collection.aggregate(shops_pipeline))
    
    # Top performing merchants
    top_merchants_pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": "$shop_id",
            "total_revenue": {"$sum": "$total_amount"},
            "order_count": {"$sum": 1}
        }},
        {"$sort": {"total_revenue": -1}},
        {"$limit": 20}
    ]
    
    top_merchants = list(Order.collection.aggregate(top_merchants_pipeline))
    
    # Get shop details for top merchants
    for merchant in top_merchants:
        shop = Shop.get_by_id(merchant['_id'])
        if shop:
            merchant['shop_name'] = shop.get('name', 'Unknown Shop')
            merchant['owner_username'] = shop.get('owner', {}).get('username', 'Unknown')
            merchant['created_at'] = shop.get('created_at')
        else:
            merchant['shop_name'] = 'Deleted Shop'
            merchant['owner_username'] = 'Unknown'
            merchant['created_at'] = None
    
    return render_template('superadmin/analytics.html',
                         revenue_data=revenue_data,
                         shops_data=shops_data,
                         top_merchants=top_merchants,
                         days=days)

@superadmin_bp.route('/orders')
@super_admin_required
@rate_limit_super_admin
def orders():
    """Super admin orders page with filtering - OPTIMIZED"""
    # Remove the expensive expired orders check from here
    # It's now handled by background task
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Build query based on status filter
    query = {}
    if status_filter != 'all':
        query["status"] = status_filter
    
    # Use estimated count for better performance on large collections
    if not query:  # No filter
        total_orders = Order.collection.estimated_document_count()
    else:
        total_orders = Order.collection.count_documents(query)
    
    total_pages = (total_orders + per_page - 1) // per_page
    
    # Get orders with pagination, only needed fields
    skip = (page - 1) * per_page
    orders = list(Order.collection.find(
        query,
        {
            "order_id": 1, "shop_id": 1, "customer_email": 1, "customer_name": 1,
            "total_amount": 1, "status": 1, "created_at": 1, "coupon": 1,
            "items": 1  # For counting items
        }
    ).sort("created_at", -1).skip(skip).limit(per_page))
    
    # Batch get shop names and owner usernames
    shop_ids = list(set(order.get('shop_id') for order in orders if order.get('shop_id')))
    shops = {}
    if shop_ids:
        shop_cursor = Shop.collection.find(
            {"_id": {"$in": shop_ids}},
            {"name": 1, "owner.username": 1}
        )
        for shop in shop_cursor:
            shops[str(shop['_id'])] = {
                'name': shop.get('name', 'Unknown Shop'),
                'owner_username': shop.get('owner', {}).get('username', 'Unknown')
            }
    
    # Add shop info to orders
    for order in orders:
        shop_id = str(order.get('shop_id', ''))
        shop_info = shops.get(shop_id, {'name': 'Unknown Shop', 'owner_username': 'Unknown'})
        order['shop_name'] = shop_info['name']
        order['owner_username'] = shop_info['owner_username']
    
    return render_template('superadmin/orders.html', 
                         orders=orders, 
                         page=page, 
                         total_pages=total_pages,
                         status_filter=status_filter,
                         total_orders=total_orders)

@superadmin_bp.route('/failed-orders')
@super_admin_required
@rate_limit_super_admin
def failed_orders():
    """Super admin failed/expired orders page"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get total count for pagination
    total_failed_orders = Order.failed_collection.count_documents({})
    total_pages = (total_failed_orders + per_page - 1) // per_page
    
    # Get failed/expired orders with pagination (sort by most recent timestamp)
    skip = (page - 1) * per_page
    failed_orders = list(Order.failed_collection.find().sort([
        ("failed_at", -1),
        ("expired_at", -1)
    ]).skip(skip).limit(per_page))
    
    # Get shop names for failed orders
    shop_ids = list(set(order.get('shop_id') for order in failed_orders if order.get('shop_id')))
    shops = {}
    if shop_ids:
        shop_cursor = Shop.collection.find({"_id": {"$in": shop_ids}})
        for shop in shop_cursor:
            shops[str(shop['_id'])] = shop.get('name', 'Unknown Shop')
    
    # Add shop names to failed orders
    for order in failed_orders:
        shop_id = str(order.get('shop_id'))
        order['shop_name'] = shops.get(shop_id, 'Unknown Shop')
    
    return render_template('superadmin/failed_orders.html', 
                         failed_orders=failed_orders, 
                         page=page, 
                         total_pages=total_pages,
                         total_failed_orders=total_failed_orders)

@superadmin_bp.route('/failed-orders/<order_id>/restore', methods=['POST'])
@super_admin_required
@rate_limit_super_admin
def restore_failed_order(order_id):
    """Restore a failed order back to pending status"""
    try:
        # Get superuser password from form
        superuser_password = request.form.get('superuser_password')
        
        if not superuser_password:
            flash('Superuser password is required for this action', 'error')
            return redirect(url_for('superadmin.failed_orders'))
        
        # Verify superuser password
        if not check_password_hash(SUPER_ADMIN_PASSWORD_HASH, superuser_password):
            flash('Invalid superuser password', 'error')
            return redirect(url_for('superadmin.failed_orders'))
        
        # Restore the failed order
        restored_order = Order.restore_failed_order(order_id)
        
        # Invalidate cache
        from .stats_cache import stats_cache
        stats_cache.invalidate_cache(['platform_stats'])
        
        # Log the restoration
        current_app.logger.info(
            f"Super admin restored failed order: {restored_order.get('order_id')} "
            f"(Shop: {restored_order.get('shop_name', 'Unknown')})"
        )
        
        flash(f'Failed order "{restored_order.get("order_id")}" has been restored to pending status.', 'success')
        
    except ValueError as e:
        flash(f'Error: {str(e)}', 'error')
    except Exception as e:
        current_app.logger.error(f"Error restoring failed order {order_id}: {e}")
        flash('An error occurred while restoring the order.', 'error')
    
    return redirect(url_for('superadmin.failed_orders'))

@superadmin_bp.route('/api/stats')
@super_admin_required
@rate_limit_super_admin
def api_stats():
    """API endpoint for real-time statistics - OPTIMIZED"""
    from .stats_cache import stats_cache
    
    # Get all stats from cache
    stats = stats_cache.get_platform_stats()
    
    return jsonify(stats)