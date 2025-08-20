from flask import render_template, request, redirect, url_for, flash, session, current_app
from models import Shop
from blueprints.auth.decorators import login_required, check_ban_status
from . import products_bp

@products_bp.route('/products')
@login_required
@check_ban_status
def products():
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.home'))
        
    all_products = shop.get('products', [])
    all_categories = shop.get('categories', [])
    
    # Add category name to each product and calculate availability
    for product in all_products:
        if product.get('category_id'):
            for category in all_categories:
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
    
    # Pagination setup
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Show 10 products per page
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '')
    
    # Filter products by search query
    if search_query:
        filtered_products = [
            p for p in all_products 
            if search_query.lower() in p.get('name', '').lower() or 
               search_query.lower() in p.get('description', '').lower()
        ]
    else:
        filtered_products = all_products
    
    # Filter by category if specified
    if category_filter:
        filtered_products = [
            p for p in filtered_products 
            if p.get('category_id') == category_filter
        ]
    
    # Calculate pagination
    total_products = len(filtered_products)
    total_pages = (total_products + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Get paginated products
    paginated_products = filtered_products[start_idx:end_idx]
    
    # Ensure page is within valid range
    if page > total_pages and total_pages > 0:
        return redirect(url_for('products.products', page=total_pages, search=search_query, category=category_filter))
    
    return render_template('merchant/products/products.html', 
                         products=paginated_products, 
                         categories=all_categories,
                         pagination={
                             'page': page,
                             'per_page': per_page,
                             'total_pages': total_pages,
                             'total_products': total_products,
                             'has_prev': page > 1,
                             'has_next': page < total_pages,
                             'prev_num': page - 1,
                             'next_num': page + 1
                         },
                         search_query=search_query,
                         selected_category=category_filter)

@products_bp.route('/add_product')
@login_required
@check_ban_status
def add_product_page():
    user_id = session.get('user_id')
    if not user_id:
        session.permanent = True
        return redirect(url_for('dashboard.home'))
    
    shop = Shop.get_by_id(user_id)
    if not shop:
        return redirect(url_for('dashboard.home'))
        
    all_categories = shop.get('categories', [])
    
    # Get category_id from query parameter if provided
    selected_category = request.args.get('category', None)
    
    return render_template('merchant/products/add_product.html', 
                           categories=all_categories,
                           selected_category=selected_category)

@products_bp.route('/products/add', methods=['POST'])
@login_required
@check_ban_status
def add_product():
    if request.method == 'POST':
        user_id = session['user_id']
        name = request.form.get('productName')
        price = request.form.get('productPrice')
        description = request.form.get('productDescription', '')
        category_id = request.form.get('productCategory') or None
        
        # Handle new stock values system
        stock_values_text = request.form.get('stockValues', '').strip()
        stock_delimiter = request.form.get('stockDelimiter', '|')
        infinite_stock = request.form.get('infiniteStock') == 'on'
        is_visible = request.form.get('isVisible') == 'on'
        
        # Calculate stock from stock values
        stock = 0
        stock_values = []
        if stock_values_text:
            if stock_delimiter == 'newline':
                stock_values = [v.strip() for v in stock_values_text.split('\n') if v.strip()]
            else:
                stock_values = [v.strip() for v in stock_values_text.split(stock_delimiter) if v.strip()]
            
            # Remove duplicates to ensure unique values only
            stock_values = list(dict.fromkeys(stock_values))  # Preserves order while removing duplicates
            
            if infinite_stock:
                stock = 999999  # Set high number for infinite stock
            else:
                stock = len(stock_values)
        elif infinite_stock:
            # Handle case where infinite_stock is True but no stock_values provided yet
            stock = 999999
        
        # Handle image upload to S3
        image_url = None
        if 'productImage' in request.files and request.files['productImage'].filename:
            file = request.files['productImage']
            
            # Make sure file position is at the beginning
            if hasattr(file, 'seek'):
                file.seek(0)
            
            from core.storage import upload_file_to_s3
            try:
                # Reset file position again before upload
                if hasattr(file, 'seek'):
                    file.seek(0)
                    
                success, result = upload_file_to_s3(file)
                if success:
                    image_url = result
                    flash("Image uploaded successfully", "success")
                else:
                    flash(result, "error")  # result contains the error message
            except Exception as e:
                flash(f"Image upload error: {str(e)[:100]}", "error")
                print(f"S3 error details: {e}")
        
        # Process duration-based pricing options if provided
        pricing_options = []
        duration_names = request.form.getlist('duration_name[]')
        duration_prices = request.form.getlist('duration_price[]')
        duration_stock_values_list = request.form.getlist('duration_stock_values[]')
        
        has_duration_pricing = duration_names and duration_prices and len(duration_names) == len(duration_prices)
        
        # If using duration pricing, calculate aggregate price and stock
        base_price = 0
        total_stock = 0
        
        if has_duration_pricing:
            for i in range(len(duration_names)):
                if duration_names[i].strip() and duration_prices[i].strip():
                    option = {
                        'name': duration_names[i].strip(),
                        'price': float(duration_prices[i])
                    }
                    
                    # Handle stock values for this option
                    option_stock_values = []
                    option_stock = 0
                    if i < len(duration_stock_values_list) and duration_stock_values_list[i].strip():
                        option_stock_values_text = duration_stock_values_list[i].strip()
                        if stock_delimiter == 'newline':
                            option_stock_values = [v.strip() for v in option_stock_values_text.split('\n') if v.strip()]
                        else:
                            option_stock_values = [v.strip() for v in option_stock_values_text.split(stock_delimiter) if v.strip()]
                        # Remove duplicates to count only unique values (preserving order)
                        unique_stock_values = list(dict.fromkeys(option_stock_values))
                        option_stock = len(unique_stock_values)
                        option_stock_values = unique_stock_values  # Store only unique values
                    
                    option['stock'] = option_stock
                    option['stock_values'] = option_stock_values
                    option['stock_delimiter'] = stock_delimiter
                    total_stock += option_stock
                        
                    # Keep track of lowest price as the base price
                    if base_price == 0 or option['price'] < base_price:
                        base_price = option['price']
                        
                    pricing_options.append(option)
            
            # Use calculated values if duration pricing is enabled
            if pricing_options:
                if not price or float(price) == 0:
                    price = base_price
                # For duration pricing products, set main stock to 0 and rely on individual option stocks
                stock = 0  # Duration pricing products don't use main stock field
                stock_values = []  # Clear main stock values when using options
        
        try:
            product = Shop.add_product(
                shop_id=user_id,
                name=name,
                price=price,
                category_id=category_id,
                image_url=image_url,
                description=description,
                stock=stock,
                stock_values=stock_values,
                stock_delimiter=stock_delimiter,
                pricing_options=pricing_options,
                infinite_stock=infinite_stock,
                is_visible=is_visible
            )
            
            flash('Product added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding product: {str(e)}', 'error')
            
        return redirect(url_for('products.add_product_page'))

@products_bp.route('/products/edit/<product_id>', methods=['POST'])
@login_required
@check_ban_status
def edit_product(product_id):
    if request.method == 'POST':
        user_id = session['user_id']
        current_app.logger.info(f"User '{user_id}' initiated edit for product '{product_id}'.")

        # Keep your optimization to get shop and products in a single query
        shop = Shop.get_by_id(user_id)
        if not shop:
            flash('Shop not found', 'error')
            current_app.logger.warning(f"Shop not found for user '{user_id}' during product edit.")
            return redirect(url_for('products.products'))

        product = next((p for p in shop.get('products', []) if str(p.get('_id')) == str(product_id)), None)

        if not product:
            flash('Product not found', 'error')
            current_app.logger.warning(f"Product '{product_id}' not found in shop for user '{user_id}'.")
            return redirect(url_for('products.products'))

        # --- Process Form Data ---
        name = request.form.get('productName')
        price_str = request.form.get('productPrice')
        price = float(price_str) if price_str else 0.0
        description = request.form.get('productDescription', '')
        category_id = request.form.get('productCategory') or None

        stock_values_text = request.form.get('stockValues', '').strip()
        stock_delimiter = request.form.get('stockDelimiter', '|')
        infinite_stock = request.form.get('infiniteStock') == 'on'
        is_visible = request.form.get('isVisible') == 'on'

        stock_values = []
        if stock_values_text:
            if stock_delimiter == 'newline':
                stock_values = [v.strip() for v in stock_values_text.split('\n') if v.strip()]
            else:
                stock_values = [v.strip() for v in stock_values_text.split(stock_delimiter) if v.strip()]
            stock_values = list(dict.fromkeys(stock_values))

        stock = len(stock_values) if not infinite_stock else 999999
        if not stock_values_text and infinite_stock:
            stock = 999999

        image_url = product.get('image_url')
        new_image_uploaded = 'productImage' in request.files and request.files['productImage'].filename

        pricing_options = []
        duration_names = request.form.getlist('duration_name[]')
        has_duration_pricing = duration_names and any(name.strip() for name in duration_names)

        if has_duration_pricing:
            duration_prices = request.form.getlist('duration_price[]')
            duration_stock_values_list = request.form.getlist('duration_stock_values[]')
            for i in range(len(duration_names)):
                if i < len(duration_names) and duration_names[i].strip():
                    option = {'name': duration_names[i].strip()}
                    option['price'] = float(duration_prices[i]) if i < len(duration_prices) and duration_prices[i] else (float(price_str) if price_str else 0)

                    option_stock_values_text = duration_stock_values_list[i].strip() if i < len(duration_stock_values_list) else ''
                    if option_stock_values_text:
                        if stock_delimiter == 'newline':
                            option_stock_values = [v.strip() for v in option_stock_values_text.split('\n') if v.strip()]
                        else:
                            option_stock_values = [v.strip() for v in option_stock_values_text.split(stock_delimiter) if v.strip()]
                        unique_values = list(dict.fromkeys(option_stock_values))
                        option['stock'] = len(unique_values)
                        option['stock_values'] = unique_values
                    else:
                        option['stock'] = 0
                        option['stock_values'] = []

                    option['stock_delimiter'] = stock_delimiter
                    pricing_options.append(option)

            if pricing_options:
                if not price_str or float(price_str) == 0:
                    price = min(opt['price'] for opt in pricing_options)
                # Per your logic, duration pricing products don't use the main stock field
                stock, stock_values = 0, []
            else:
                has_duration_pricing = False

        # --- Track Changes ---
        changes = []
        if name != product.get('name'): changes.append('name')
        if description != product.get('description', ''): changes.append('description')
        if is_visible != product.get('is_visible', False): changes.append('visibility')
        if (category_id or None) != (product.get('category_id') or None): changes.append('category')
        if abs(price - float(product.get('price', 0.0))) > 1e-9: changes.append('price')
        if new_image_uploaded: changes.append('image')

        stock_details_changed = (
                infinite_stock != product.get('infinite_stock', False) or
                stock_values != product.get('stock_values', []) or
                pricing_options != product.get('pricing_options', [])
        )
        if stock_details_changed: changes.append('stock')

        if not changes:
            flash('No changes were made to the product.', 'info')
            current_app.logger.info(f"No changes detected for product '{product_id}'. Update aborted.")
            return redirect(url_for('products.products'))

        current_app.logger.info(f"Detected changes for product '{product_id}': {', '.join(changes)}")

        if new_image_uploaded:
            file = request.files['productImage']
            file.seek(0)
            from core.storage import upload_file_to_s3
            try:
                success, result = upload_file_to_s3(file)
                if success:
                    image_url = result
                    current_app.logger.info(f"Successfully uploaded new image for product '{product_id}'.")
                else:
                    flash(f"Image upload failed: {result}", "error")
                    current_app.logger.error(f"Image upload failed for product '{product_id}': {result}")
            except Exception as e:
                flash(f"Image upload error: {str(e)[:100]}", "error")
                current_app.logger.error(f"Image upload exception for product '{product_id}': {e}", exc_info=True)

        try:
            Shop.update_product(
                shop_id=user_id, product_id=product_id, name=name, price=price,
                description=description, stock=stock, stock_values=stock_values,
                stock_delimiter=stock_delimiter, category_id=category_id, image_url=image_url,
                pricing_options=pricing_options, infinite_stock=infinite_stock, is_visible=is_visible
            )
            current_app.logger.info(f"Successfully updated product '{product_id}' in the database.")

            # --- Universal Specific Flash Message Logic ---
            if len(changes) == 1:
                changed_item = changes[0]
                message = ''
                if changed_item == 'visibility':
                    message = "Product is now visible." if is_visible else "Product is now hidden."
                elif changed_item == 'image':
                    message = "Product image has been updated."
                elif changed_item == 'stock':
                    message = "Product stock details have been updated."
                else:
                    message = f"Product {changed_item} has been updated."
                flash(message, 'success')
            else:
                flash('Product updated successfully!', 'success')

        except ValueError as e:
            flash(f'Error updating product: {str(e)}', 'error')
            current_app.logger.error(f"Database update failed for product '{product_id}': {e}", exc_info=True)

        return redirect(url_for('products.products'))

@products_bp.route('/products/delete/<product_id>', methods=['POST'])
@login_required
@check_ban_status
def delete_product(product_id):
    user_id = session['user_id']
    
    # OPTIMIZATION: Get shop and product in single query
    shop = Shop.get_by_id(user_id)
    if not shop:
        flash('Shop not found', 'error')
        return redirect(url_for('products.products'))
    
    # Find product in shop data (no separate query)
    product = None
    for p in shop.get('products', []):
        if str(p['_id']) == str(product_id):
            product = p
            break
    
    # Check if product exists
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('products.products'))
    
    try:
        # Delete product image from S3 if it exists
        if product.get('image_url'):
            from core.storage import delete_file_from_s3
            delete_file_from_s3(product['image_url'])
            
        Shop.delete_product(user_id, product_id)
        flash('Product deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting product: {str(e)}', 'error')
        
    return redirect(url_for('products.products')) 