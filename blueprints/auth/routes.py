from flask import render_template, request, redirect, url_for, flash, session
from models import Shop
from . import auth_bp
from core.cloudflare.verifier import CloudflareVerifier

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

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
        
    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email')
        password = request.form.get('password')
        
        # Try to find shop by email first, then by username
        shop = Shop.get_by_email(username_or_email)
        if not shop:
            shop = Shop.get_by_username(username_or_email)
        
        if shop and Shop.check_password(shop['_id'], password):
            # Track the login attempt with proper IP detection
            ip_address = get_client_ip()
            Shop.track_login(shop['_id'], ip_address)
            
            # Make session permanent to last for the configured lifetime
            session.permanent = True
            session['user_id'] = str(shop['_id'])
            session['username'] = shop['owner']['username']
            session['shop_name'] = shop['name']
            flash('Log in successful!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash('Invalid username/email or password', 'error')
    
    # Redirect to homepage instead of rendering login page
    return redirect(url_for('dashboard.home'))

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        shop_name = request.form.get('shop_name')
        captcha_token = request.form.get('captcha_token')
        
        # Validate inputs
        if not username or not email or not password or not shop_name:
            flash('All fields are required', 'error')
            return redirect(url_for('dashboard.home'))
            
        if not captcha_token:
            flash('Please complete the captcha verification', 'error')
            return redirect(url_for('dashboard.home'))
        
        # Verify captcha
        client_ip = get_client_ip()
        captcha_result = CloudflareVerifier.verify_token(captcha_token, client_ip)
        
        if not captcha_result.get('success'):
            flash('Captcha verification failed. Please try again.', 'error')
            return redirect(url_for('dashboard.home'))
            
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('dashboard.home'))
            
        try:
            shop = Shop.create(username, email, password, shop_name)
            
            # Track the initial login after account creation with proper IP detection
            ip_address = get_client_ip()
            Shop.track_login(shop['_id'], ip_address)
            
            session.permanent = True
            session['user_id'] = str(shop['_id'])
            session['username'] = shop['owner']['username']
            session['shop_name'] = shop['name']
            flash('Account created successfully!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        except ValueError as e:
            error_message = str(e)
            # Check if it's a reserved username error
            if "reserved username" in error_message.lower():
                # Store form data in session for preservation (except username)
                session['signup_form_data'] = {
                    'email': email,
                    'shop_name': shop_name,
                    'error_message': error_message
                }
                flash(error_message, 'error')
                return redirect(url_for('dashboard.home'))
            else:
                flash(error_message, 'error')
                return redirect(url_for('dashboard.home'))
    
    # Redirect to homepage instead of rendering signup page
    return redirect(url_for('dashboard.home'))

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    # This route only renders the template with a "coming soon" message
    # In the future, this will handle password reset functionality
    if request.method == 'POST':
        # This is a placeholder for future implementation
        flash('Password reset functionality coming soon', 'info')
        
    # Redirect to homepage instead of rendering forgot password page
    return redirect(url_for('dashboard.home'))

@auth_bp.route('/clear-signup-form-data', methods=['POST'])
def clear_signup_form_data():
    """Clear signup form data from session"""
    if 'signup_form_data' in session:
        del session['signup_form_data']
    return '', 204

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('dashboard.home')) 