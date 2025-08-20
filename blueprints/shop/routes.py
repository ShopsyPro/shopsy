from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from models import Shop
from blueprints.auth.decorators import login_required, check_ban_status
from . import shop_bp
import json
from bson import ObjectId

# Helper function to convert MongoDB objects to JSON
def mongo_to_json(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

@shop_bp.route('/myshop')
@login_required
@check_ban_status
def myshop():
    user_id = session['user_id']
    username = session['username']
    shop_name = session['shop_name']
    
    shop = Shop.get_by_id(user_id)
    if not shop:
        return redirect(url_for('dashboard.home'))
    
    # Get active products for the shop view (merchants see all products regardless of visibility)
    all_products_data = [] # Renamed to avoid confusion with the variable name in template
    for product in shop.get('products', []):
        # Auto-determine availability based on stock (merchants see all products regardless of visibility)
        is_available = product.get('infinite_stock') or (product.get('stock', 0) > 0) or (product.get('has_duration_pricing') and any(option.get('stock', 0) > 0 for option in product.get('pricing_options', [])))
        if is_available:
            if product.get('category_id'):
                for category in shop.get('categories', []):
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

            all_products_data.append(product)
    
    shop_url = f"{request.host_url}{username}"
    all_categories = shop.get('categories', [])
    selected_category_id = request.args.get('category')

    if selected_category_id:
        filtered_products = [p for p in all_products_data if str(p.get('category_id')) == str(selected_category_id)]
    else:
        filtered_products = all_products_data

    return render_template('merchant/myshop.html', 
                          products=filtered_products,
                          shop_name=shop_name,
                          shop_url=shop_url,
                          categories=all_categories,
                          selected_category=selected_category_id,
                          username=username # Pass username for product_detail URL
                          )

@shop_bp.route('/settings')
@login_required
@check_ban_status
def settings():
    user_id = session['user_id']
    user = Shop.get_by_id(user_id)
    if not user:
        return redirect(url_for('dashboard.home'))
    return render_template('merchant/settings/settings.html', user=user)

@shop_bp.route('/settings/update', methods=['POST'])
@login_required
@check_ban_status
def update_settings():
    user_id = session['user_id']
    
    if request.method == 'POST':
        email = request.form.get('email')
        shop_name = request.form.get('shop_name')
        shop_description = request.form.get('shop_description')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        email_password = request.form.get('email_password')  # Password for email changes
        
        # Get current user data to compare changes
        current_user = Shop.get_by_id(user_id)
        if not current_user:
            flash('User not found', 'error')
            return redirect(url_for('shop.settings'))
            
        current_email = current_user.get('owner', {}).get('email', '')
        current_shop_name = current_user.get('name', '')
        current_shop_description = current_user.get('description', 'Welcome to our digital marketplace!')
        
        # Handle email update (requires password verification)
        if email and email.strip() != current_email:
            if not email_password:
                flash('Password is required to change email address', 'error')
                return redirect(url_for('shop.settings'))
                
            if not Shop.check_password(user_id, email_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('shop.settings'))
                
            try:
                Shop.update_owner(user_id, email=email)
                flash('Email updated successfully!', 'success')
            except Exception as e:
                flash(f'Error updating email: {str(e)}', 'error')
        
        # Handle shop name update (separate from email)
        if shop_name and shop_name.strip() != current_shop_name:
            try:
                Shop.update_shop(user_id, name=shop_name)
                session['shop_name'] = shop_name
                flash('Shop name updated successfully!', 'success')
            except Exception as e:
                flash(f'Error updating shop name: {str(e)}', 'error')
        
        # Handle shop description update
        if shop_description and shop_description.strip() != current_shop_description:
            try:
                Shop.update_shop(user_id, description=shop_description)
                flash('Shop description updated successfully!', 'success')
            except Exception as e:
                flash(f'Error updating shop description: {str(e)}', 'error')
        
        # Handle avatar upload
        if 'avatar' in request.files and request.files['avatar'].filename:
            file = request.files['avatar']
            if hasattr(file, 'seek'):
                file.seek(0)
            
            from core.storage import upload_file_to_s3
            try:
                if hasattr(file, 'seek'):
                    file.seek(0)
                    
                success, result = upload_file_to_s3(file, folder="avatars")
                if success:
                    avatar_url = result
                    # Delete old avatar if it exists and is not the default
                    old_avatar = current_user.get('avatar_url')
                    if old_avatar and '/static/assets/default_avatar.png' not in old_avatar:
                        from core.storage import delete_file_from_s3
                        delete_file_from_s3(old_avatar)
                    
                    Shop.update_shop(user_id, avatar_url=avatar_url)
                    flash('Avatar updated successfully!', 'success')
                else:
                    flash(result, 'error')  # result contains the error message
            except Exception as e:
                flash(f'Error uploading avatar: {str(e)}', 'error')
                
        # Handle password change
        if current_password and new_password:
            if not Shop.check_password(user_id, current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('shop.settings'))
                
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('shop.settings'))
                
            try:
                Shop.update_owner(user_id, password=new_password)
                flash('Password changed successfully!', 'success')
            except Exception as e:
                flash(f'Error changing password: {str(e)}', 'error')
        
    return redirect(url_for('shop.settings'))

@shop_bp.route('/api/check-store', methods=['POST'])
def check_store():
    """Check if a store exists by username"""
    data = request.json
    if not data:
        return jsonify({
            'success': False,
            'message': 'Invalid request'
        }), 400
    
    username = data.get('username', '').strip().lower()
    
    if not username:
        return jsonify({
            'success': False,
            'message': 'Enter store username'
        }), 400
    
    # Check if shop exists
    shop = Shop.get_by_username(username)
    if shop:
        return jsonify({
            'success': True,
            'shop_name': shop['name'],
            'username': username,
            'redirect_url': f'/{username}'
        })
    else:
        return jsonify({
            'success': False,
            'message': f'Store "{username}" not found'
        })

# Client-facing shop routes
@shop_bp.route('/<username>')
def shop(username):
    user = Shop.get_by_username(username)
    if not user:
        return render_template('error/404.html'), 404
    
    # Check if shop is banned - hide banned shops from public
    if user.get('banned'):
        return render_template('error/404.html'), 404
        
    user_id = str(user['_id'])
    shop_name = user['name']
    
    # Get online status for this merchant
    online_status = Shop.get_online_status(user_id)
    last_online_message = Shop.get_last_online_message(user_id)
    
    # Get filter parameters
    category_id = request.args.get('category_id')
    search_query = request.args.get('search', '').strip().lower()
    
    # OPTIMIZATION: Pre-filter products more efficiently
    all_products = user.get('products', [])
    products = []
    
    # Calculate category product counts for filtering empty categories and coupons
    category_product_counts = {}
    for product in all_products:
        # Only count visible and available products
        is_visible = product.get('is_visible', True)
        is_available = product.get('infinite_stock') or (product.get('stock', 0) > 0) or (product.get('has_duration_pricing') and any(option.get('stock', 0) > 0 for option in product.get('pricing_options', [])))
        
        if is_visible and is_available:
            cat_id = product.get('category_id')
            if cat_id:
                category_product_counts[cat_id] = category_product_counts.get(cat_id, 0) + 1

    # Get public coupons (only for categories with products)
    public_coupons = []
    all_coupons = user.get('coupons', [])
    now = datetime.utcnow()
    
    for coupon in all_coupons:
        # Only include active public coupons that are not expired
        if (coupon.get('is_public') and 
            coupon.get('status') == 'Active' and 
            coupon.get('expiry_date') > now):
            
            # Check if coupon is for a category with products
            coupon_category_id = coupon.get('category_id')
            if coupon_category_id:
                # Only include if the category has at least one product
                if category_product_counts.get(coupon_category_id, 0) > 0:
                    # Add category name to coupon
                    for category in user.get('categories', []):
                        if str(category['_id']) == coupon_category_id:
                            coupon['category_name'] = category['name']
                            break
                    else:
                        coupon['category_name'] = 'ALL'
                    public_coupons.append(coupon)
            else:
                # Coupon for all products - include it
                public_coupons.append(coupon)
    
    # OPTIMIZATION: Single pass filtering with early exit
    for product in all_products:
        # Skip products that are not visible or don't have stock
        is_visible = product.get('is_visible', True)  # Default to True for existing products
        is_available = product.get('infinite_stock') or (product.get('stock', 0) > 0) or (product.get('has_duration_pricing') and any(option.get('stock', 0) > 0 for option in product.get('pricing_options', [])))
        if not is_visible or not is_available:
            continue
            
        # Apply category filter if specified
        if category_id and str(product.get('category_id')) != str(category_id):
            continue
            
        # Apply search filter if specified
        if search_query:
            name_match = search_query in product.get('name', '').lower()
            desc_match = search_query in product.get('description', '').lower()
            if not (name_match or desc_match):
                continue
            
        # Add category name to product
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
                
        products.append(product)
            
    # Get all categories for this shop and filter out empty ones
    all_categories = user.get('categories', [])
    categories = []
    
    # Only include categories that have at least one visible/available product
    for category in all_categories:
        cat_id = str(category['_id'])
        if category_product_counts.get(cat_id, 0) > 0:
            categories.append(category)
    
    # Find current category name if filtering
    current_category_name = 'All Products'
    if category_id:
        for cat in categories:
            if str(cat['_id']) == str(category_id):
                current_category_name = cat['name']
                break
                
    # Update page title based on filters
    title = current_category_name
    if search_query:
        title = f"Search: {search_query}"
        if category_id:
            title = f"{current_category_name} - {title}"
    
    # Determine theme to use with new theme names
    theme = Shop.get_theme(user_id)
    template_path = f'themes/{theme}.html'
    
    # Fallback to classic theme if theme template doesn't exist
    try:
        # Test if template exists by trying to get the template
        from flask import current_app
        current_app.jinja_env.get_template(template_path)
    except:
        template_path = 'themes/classic.html'  # Fallback to classic theme
    
    return render_template(template_path, 
                          shop_name=shop_name,
                          username=username,
                          products=products,
                          categories=categories,
                          current_category_name=title,
                          search_query=search_query,
                          public_coupons=public_coupons,
                          shop_avatar_url=user.get('avatar_url'),
                          shop_description=user.get('description', 'Welcome to our digital marketplace!'),
                          online_status=online_status,
                          last_online_message=last_online_message)

@shop_bp.route('/api/product/<username>/<product_id>', methods=['GET'])
def get_product_details(username, product_id):
    """Get product details for modal display"""
    shop = Shop.get_by_username(username)
    if not shop:
        return jsonify({'error': 'Shop not found'}), 404
        
    product = Shop.get_product(shop['_id'], product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
        
    # Auto-determine availability based on stock and visibility
    is_visible = product.get('is_visible', True)
    is_available = product.get('infinite_stock') or (product.get('stock', 0) > 0) or (product.get('has_duration_pricing') and any(option.get('stock', 0) > 0 for option in product.get('pricing_options', [])))
    if not is_visible or not is_available:
        return jsonify({'error': 'Product not available'}), 404
        
    # Add category name
    if product.get('category_id'):
        for category in shop.get('categories', []):
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
        
    return jsonify({
        'success': True,
        'product': json.loads(json.dumps(product, default=mongo_to_json)),
        'shop_name': shop['name']
    })

@shop_bp.route('/api/online-status/<username>', methods=['GET'])
def get_online_status(username):
    """Get online status of a merchant"""
    shop = Shop.get_by_username(username)
    if not shop:
        return jsonify({'error': 'Shop not found'}), 404
    
    online_status = Shop.get_online_status(shop['_id'])
    last_online_data = Shop.get_last_online_data(shop['_id'])
    
    return jsonify({
        'success': True,
        'online_status': online_status,
        'last_online_message': last_online_data['message'],
        'last_online_status': last_online_data['status'],
        'last_activity': last_online_data.get('last_activity'),
        'last_login': shop.get('login_tracking', {}).get('last_login'),
        'hours_ago': last_online_data['hours_ago'],
        'days_ago': last_online_data['days_ago']
    }) 