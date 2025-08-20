from flask import render_template, request, redirect, url_for, flash, session, jsonify
from models import Shop
from blueprints.auth.decorators import login_required, check_ban_status
from . import categories_bp

@categories_bp.route('/categories')
@login_required
@check_ban_status
def categories():
    user_id = session['user_id']
    shop = Shop.get_by_id(user_id)
    
    if not shop:
        return redirect(url_for('dashboard.home'))
        
    all_categories = shop.get('categories', [])
    
    # Count products in each category
    for category in all_categories:
        product_count = len([p for p in shop.get('products', []) if p.get('category_id') == str(category['_id'])])
        category['product_count'] = product_count
    
    return render_template('merchant/products/categories.html', categories=all_categories)

@categories_bp.route('/categories/add', methods=['POST'])
@login_required
@check_ban_status
def add_category():
    if request.method == 'POST':
        user_id = session['user_id']
        name = request.form.get('categoryName')
        description = request.form.get('categoryDescription', '')
        
        try:
            category = Shop.add_category(
                shop_id=user_id,
                name=name,
                description=description
            )
            
            # Check if this is an AJAX request (from quick create)
            if request.args.get('ajax') == 'true':
                # This is an AJAX call, return JSON
                return jsonify({
                    'success': True,
                    'message': 'Category added successfully!',
                    'category': {
                        'id': str(category['_id']),
                        'name': category['name'],
                        'description': category.get('description', '')
                    }
                })
            
            flash('Category added successfully!', 'success')
        except Exception as e:
            # Check if this is an AJAX request
            if request.args.get('ajax') == 'true':
                return jsonify({
                    'success': False,
                    'message': f'Error adding category: {str(e)}'
                }), 400
            
            flash(f'Error adding category: {str(e)}', 'error')
            
        return redirect(url_for('categories.categories'))

@categories_bp.route('/categories/edit/<category_id>', methods=['POST'])
@login_required
@check_ban_status
def edit_category(category_id):
    if request.method == 'POST':
        user_id = session['user_id']
        category = Shop.get_category(user_id, category_id)
        
        # Check if category exists
        if not category:
            flash('Category not found', 'error')
            return redirect(url_for('categories.categories'))
            
        name = request.form.get('categoryName')
        description = request.form.get('categoryDescription', '')
        
        try:
            Shop.update_category(
                shop_id=user_id,
                category_id=category_id,
                name=name,
                description=description
            )
            flash('Category updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating category: {str(e)}', 'error')
            
        return redirect(url_for('categories.categories'))

@categories_bp.route('/categories/delete/<category_id>', methods=['POST'])
@login_required
@check_ban_status
def delete_category(category_id):
    user_id = session['user_id']
    category = Shop.get_category(user_id, category_id)
    
    # Check if category exists
    if not category:
        flash('Category not found', 'error')
        return redirect(url_for('categories.categories'))
        
    try:
        Shop.delete_category(user_id, category_id)
        flash('Category deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting category: {str(e)}', 'error')
        
    return redirect(url_for('categories.categories')) 