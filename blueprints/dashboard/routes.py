from flask import render_template, session, redirect, url_for, request, jsonify
from datetime import datetime
from models import Shop, Order
from blueprints.auth.decorators import login_required, check_ban_status
from . import dashboard_bp
import json
from bson import ObjectId

# Helper function to convert MongoDB objects to JSON
def mongo_to_json(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

@dashboard_bp.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
    
    # Get current domain for dynamic URL preview
    from flask import request
    current_domain = request.host
    
    return render_template('_base/homepage.html', now=datetime.utcnow(), current_domain=current_domain)

@dashboard_bp.route('/dashboard')
@login_required
@check_ban_status
def dashboard():
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.home'))
    
    # Get counts
    products_count = len(shop.get('products', []))
    products = shop.get('products', [])

    # Count how many are out of stock
    out_of_stock_count = 0
    for p in products:
        if p.get('has_duration_pricing') and p.get('pricing_options'):
            # For duration pricing products, check if any option has stock
            has_stock = any(option.get('stock', 0) > 0 for option in p.get('pricing_options', []))
            if not has_stock:
                out_of_stock_count += 1
        else:
            # For regular products, check main stock
            if p.get('stock', 0) == 0:
                out_of_stock_count += 1
    
    # Get coupon information
    all_coupons = shop.get('coupons', [])
    now = datetime.utcnow()
    active_count = 0
    expired_count = 0
    
    # Check coupon expiry status
    for coupon in all_coupons:
        is_expired = coupon.get('expiry_date') < now
        
        # If expired but still marked active, update the status
        if is_expired and coupon.get('status') == 'Active':
            Shop.update_coupon(user_id, str(coupon['_id']), status='Expired')
            coupon['status'] = 'Expired'
        
        # Count active and expired coupons
        if coupon.get('status') == 'Active':
            active_count += 1
        elif coupon.get('status') == 'Expired' or is_expired:
            expired_count += 1
    
    # Get orders count and revenue data, but ONLY for completed orders
    all_orders = Order.get_by_shop(user_id)
    completed_orders = [order for order in all_orders if order.get('status') == 'completed']
    orders_count = len(completed_orders)
    
    # Get weekly revenue data
    weekly_revenue = Shop.get_revenue_by_timeframe(user_id, 7)
    total_weekly_revenue = sum(item['total'] for item in weekly_revenue)
    
    # Get recent activity from the last 24 hours
    recent_activities = Shop.get_recent_activities(user_id, 24)
    
    return render_template('merchant/dashboard.html', 
                           products_count=products_count, 
                           out_of_stock_count= out_of_stock_count,
                           active_coupons=active_count,
                           expired_coupons=expired_count,
                           orders_count=orders_count,
                           total_revenue=total_weekly_revenue,
                           weekly_revenue=weekly_revenue,
                           recent_activities=recent_activities) 

@dashboard_bp.route('/activity_history')
@login_required
@check_ban_status
def activity_history():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get all activities for this user
    all_activities = Shop.get_recent_activities(user_id, hours=24*30)  # Last 30 days
    
    # Calculate pagination
    total_activities = len(all_activities)
    total_pages = (total_activities + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Get paginated activities
    paginated_activities = all_activities[start_idx:end_idx]
    
    return render_template('merchant/activity/activity_history.html', 
                           activities=paginated_activities,
                           current_page=page,
                           total_pages=total_pages,
                           total_activities=total_activities)

# API endpoints for dashboard
@dashboard_bp.route('/api/revenue/<int:days>', methods=['GET'])
@login_required
@check_ban_status
def get_revenue_data(days):
    user_id = session['user_id']
    revenue_data = Shop.get_revenue_by_timeframe(user_id, days)
    # Calculate the total revenue
    total_revenue = sum(item['total'] for item in revenue_data)
    return jsonify({
        'revenue_data': json.loads(json.dumps(revenue_data, default=mongo_to_json)),
        'total_revenue': total_revenue
    })

@dashboard_bp.route('/api/activity', methods=['GET'])
@login_required
@check_ban_status
def get_recent_activity():
    user_id = session['user_id']
    hours = request.args.get('hours', 24, type=int)
    print(f"API: Getting recent activities for user {user_id}, hours={hours}")
    
    try:
        activities = Shop.get_recent_activities(user_id, hours)
        print(f"API: Found {len(activities)} activities")
        
        # Make sure activities are sorted by timestamp (newest first)
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Convert to JSON-friendly format
        activities_json = json.loads(json.dumps(activities, default=mongo_to_json))
        
        print(f"API: First activity timestamp: {activities[0]['timestamp'] if activities else 'No activities'}")
        
        return jsonify({
            'activities': activities_json,
            'count': len(activities)
        })
    except Exception as e:
        print(f"API error getting activity: {e}")
        return jsonify({
            'activities': [],
            'count': 0,
            'error': str(e)
        }), 500 