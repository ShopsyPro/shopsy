import functools
from flask import session, redirect, url_for, request
from models import CustomerOTP
import logging

logger = logging.getLogger(__name__)

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def check_ban_status(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            from models import Shop
            user = Shop.get_by_id(session['user_id'])
            if user and user.get('banned'):
                session.clear()
                return redirect(url_for('merchant.banned'))
        return f(*args, **kwargs)
    return decorated_function

def customer_session_required(f):
    """Decorator to validate customer session and prevent backstack issues"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if customer is authenticated via OTP
        customer_email = session.get('customer_email')
        customer_otp_verified = session.get('customer_otp_verified', False)
        
        if not customer_email or not customer_otp_verified:
            # Clear any stale session data
            session.pop('customer_email', None)
            session.pop('customer_otp_verified', None)
            session.pop('customer_orders', None)
            
            # Redirect to track orders page for re-authentication
            return redirect(url_for('orders.track_orders'))
        
        # Validate OTP session hasn't expired (30 minutes)
        otp_timestamp = session.get('customer_otp_timestamp')
        if otp_timestamp:
            from datetime import datetime, timedelta
            otp_time = datetime.fromtimestamp(otp_timestamp)
            if datetime.utcnow() - otp_time > timedelta(minutes=30):
                # Session expired, clear and redirect
                session.pop('customer_email', None)
                session.pop('customer_otp_verified', None)
                session.pop('customer_orders', None)
                session.pop('customer_otp_timestamp', None)
                return redirect(url_for('orders.track_orders'))
        
        # Add cache-busting parameter to prevent back/forward navigation issues
        if request.method == 'GET' and not request.args.get('_t'):
            # Add timestamp parameter to force fresh page load
            import time
            timestamp = int(time.time())
            return redirect(request.url + ('&' if '?' in request.url else '?') + f'_t={timestamp}')
        
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        from models import Shop
        user = Shop.get_by_id(session['user_id'])
        if not user or not user.get('is_superadmin'):
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function 