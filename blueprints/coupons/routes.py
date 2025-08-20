from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from models import Shop
from blueprints.auth.decorators import login_required, check_ban_status
from . import coupons_bp

@coupons_bp.route('/coupons')
@login_required
@check_ban_status
def coupons():
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.home'))
        
    all_coupons = shop.get('coupons', [])
    all_categories = shop.get('categories', [])
    
    # Get all coupon usage counts in a single query to avoid N+1 problem
    usage_counts = Shop.get_all_coupon_usage_counts(user_id)
    
    # Check each coupon and update status if expired
    now = datetime.utcnow()
    expired_count = 0
    active_count = 0
    total_usages = 0
    
    for coupon in all_coupons:
        # Check if coupon is expired based on date
        is_expired = coupon.get('expiry_date') < now
        
        # If expired but still marked active, update the status in the database
        if is_expired and coupon.get('status') == 'Active':
            Shop.update_coupon(user_id, str(coupon['_id']), status='Expired')
            coupon['status'] = 'Expired'  # Update in memory too
        
        # Count active and expired coupons
        if coupon.get('status') == 'Active':
            active_count += 1
        elif coupon.get('status') == 'Expired' or is_expired:
            expired_count += 1
        
        # Add category name to coupon
        if coupon.get('category_id'):
            for category in all_categories:
                if str(category['_id']) == coupon['category_id']:
                    coupon['category_name'] = category['name']
                    break
            else:
                coupon['category_name'] = 'ALL'
        else:
            coupon['category_name'] = 'ALL'
        
        # Get usage count from the pre-fetched data
        usage_count = usage_counts.get(str(coupon['_id']), 0)
        coupon['usage_count'] = usage_count
        total_usages += usage_count
    
    return render_template('merchant/coupons/coupons.html', 
                          coupons=all_coupons,
                          categories=all_categories,
                          active_coupons=active_count,
                          expired_coupons=expired_count,
                          total_usages=total_usages)

@coupons_bp.route('/coupons/add', methods=['POST'])
@login_required
@check_ban_status
def add_coupon():
    if request.method == 'POST':
        user_id = session['user_id']
        code = request.form.get('couponCode')
        coupon_type = request.form.get('couponType', 'percentage')
        discount_value = request.form.get('discountValue')
        expiry_date = request.form.get('expiryDate')
        category_id = request.form.get('couponCategory') or None
        is_public = 'isPublic' in request.form
        
        conditional_value = request.form.get('conditionalValue')
        max_cap = conditional_value if coupon_type == 'percentage' and conditional_value else None
        min_order_value = conditional_value if coupon_type == 'fixed' and conditional_value else None
        
        is_ajax = request.args.get('ajax') == 'true'

        try:
            new_coupon = Shop.add_coupon(
                shop_id=user_id,
                code=code,
                coupon_type=coupon_type,
                discount_value=discount_value,
                expiry_date=expiry_date,
                category_id=category_id,
                is_public=is_public,
                max_cap=max_cap,
                min_order_value=min_order_value
            )
            
            if is_ajax:
                # Convert ObjectId fields to strings for JSON serialization
                coupon_data = {
                    "id": str(new_coupon["_id"]),
                    "code": new_coupon["code"],
                    "type": new_coupon["type"],
                    "discount_value": new_coupon["discount_value"],
                    "expiry_date": new_coupon["expiry_date"].isoformat() if new_coupon.get("expiry_date") else None,
                    "category_id": new_coupon.get("category_id"),
                    "status": new_coupon.get("status"),
                    "is_public": new_coupon.get("is_public"),
                    "created_at": new_coupon["created_at"].isoformat() if new_coupon.get("created_at") else None
                }
                return jsonify({"success": True, "message": "Coupon added successfully!", "coupon": coupon_data})
            flash('Coupon added successfully!', 'success')
        except Exception as e:
            if is_ajax:
                return jsonify({"success": False, "message": str(e)})
            flash(f'Error adding coupon: {str(e)}', 'error')
            
        return redirect(url_for('coupons.coupons'))

@coupons_bp.route('/coupons/edit/<coupon_id>', methods=['POST'])
@login_required
@check_ban_status
def edit_coupon(coupon_id):
    if request.method == 'POST':
        user_id = session['user_id']
        coupon = Shop.get_coupon(user_id, coupon_id)
        
        # Check if coupon exists
        if not coupon:
            flash('Coupon not found', 'error')
            return redirect(url_for('coupons.coupons'))
            
        code = request.form.get('couponCode')
        coupon_type = request.form.get('couponType', 'percentage')
        discount_value = request.form.get('discountValue')
        expiry_date = request.form.get('expiryDate')
        status = request.form.get('couponStatus', 'Active')
        category_id = request.form.get('couponCategory') or None
        is_public = 'isPublic' in request.form
        conditional_value = request.form.get('conditionalValue')
        max_cap = conditional_value if coupon_type == 'percentage' else None
        min_order_value = conditional_value if coupon_type == 'fixed' else None
        
        try:
            # Convert expiry_date string to datetime
            expiry_datetime = datetime.strptime(expiry_date, "%Y-%m-%d")
            
            # Prepare update data
            update_data = {
                'code': code.upper(),
                'type': coupon_type,
                'discount_value': float(discount_value),
                'expiry_date': expiry_datetime,
                'status': status,
                'category_id': category_id,
                'is_public': is_public
            }
            
            # Add max_cap for percentage coupons
            if coupon_type == 'percentage' and max_cap:
                update_data['max_cap'] = float(max_cap)
            elif coupon_type == 'fixed':
                update_data['max_cap'] = None  # Remove max_cap for fixed coupons
            
            # Add min_order_value for fixed coupons
            if coupon_type == 'fixed' and min_order_value:
                update_data['min_order_value'] = float(min_order_value)
            elif coupon_type == 'percentage':
                update_data['min_order_value'] = None  # Remove min_order_value for percentage coupons
            
            # Keep backward compatibility with discount_percentage field
            if coupon_type == 'percentage':
                update_data['discount_percentage'] = float(discount_value)  # Changed from int to float
            else:
                update_data['discount_percentage'] = 0
            
            Shop.update_coupon(
                shop_id=user_id,
                coupon_id=coupon_id,
                **update_data
            )
            flash('Coupon updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating coupon: {str(e)}', 'error')
            
        return redirect(url_for('coupons.coupons'))

@coupons_bp.route('/coupons/delete/<coupon_id>', methods=['POST'])
@login_required
@check_ban_status
def delete_coupon(coupon_id):
    user_id = session['user_id']
    coupon = Shop.get_coupon(user_id, coupon_id)
    
    # Check if coupon exists
    if not coupon:
        flash('Coupon not found', 'error')
        return redirect(url_for('coupons.coupons'))
        
    try:
        Shop.delete_coupon(user_id, coupon_id)
        flash('Coupon deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting coupon: {str(e)}', 'error')
        
    return redirect(url_for('coupons.coupons')) 