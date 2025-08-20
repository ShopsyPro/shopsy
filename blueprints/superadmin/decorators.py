import os
import hashlib
import hmac
import time
from functools import wraps
from flask import request, session, redirect, url_for, abort, current_app
from werkzeug.security import check_password_hash, generate_password_hash

# Super Admin Configuration
SUPER_ADMIN_USERNAME = os.getenv('SUPER_ADMIN_USERNAME', 'admin')
SUPER_ADMIN_PASSWORD_HASH = os.getenv('SUPER_ADMIN_PASSWORD_HASH', 
    generate_password_hash('admin123', method='pbkdf2:sha256'))
SUPER_ADMIN_SECRET_KEY = os.getenv('SUPER_ADMIN_SECRET_KEY', 'your-super-secret-key-change-in-production')

# IP Whitelist - Only these IPs can access super admin
ALLOWED_IPS = {
    '127.0.0.1',      # localhost
    '::1',            # localhost IPv6
}

# Add custom IP from environment variable
CUSTOM_IP = os.getenv('SUPER_ADMIN_ALLOWED_IP')
if CUSTOM_IP:
    ALLOWED_IPS.add(CUSTOM_IP)

def get_client_ip():
    """Get the real client IP address with enhanced VPN/proxy detection"""
    # Check for Cloudflare first (most reliable for Cloudflare setups)
    cf_connecting_ip = request.headers.get('CF-Connecting-Ip')
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    
    # Check for other proxy headers in order of reliability
    headers_to_check = [
        'X-Real-IP',
        'X-Forwarded-For',
        'X-Client-IP',
        'X-Forwarded',
        'Forwarded-For',
        'Forwarded'
    ]
    
    for header in headers_to_check:
        ip = request.headers.get(header)
        if ip:
            # Handle comma-separated lists (take the first one)
            if ',' in ip:
                ip = ip.split(',')[0].strip()
            return ip.strip()
    
    # Fallback to remote_addr
    return request.remote_addr

def is_ip_allowed(ip_address):
    """Check if IP address is in the whitelist"""
    return ip_address in ALLOWED_IPS

def generate_super_admin_token(username, timestamp):
    """Generate a secure token for super admin authentication"""
    message = f"{username}:{timestamp}:{SUPER_ADMIN_SECRET_KEY}"
    return hmac.new(
        SUPER_ADMIN_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def verify_super_admin_token(token, username, timestamp):
    """Verify the super admin authentication token"""
    expected_token = generate_super_admin_token(username, timestamp)
    return hmac.compare_digest(token, expected_token)

def super_admin_required(f):
    """Decorator to require super admin authentication with IP whitelist"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check IP whitelist first
        client_ip = get_client_ip()
        
        # Debug logging to help troubleshoot IP detection
        current_app.logger.info(f"Super admin access attempt from IP: {client_ip}")
        current_app.logger.info(f"Allowed IPs: {ALLOWED_IPS}")
        
        # Log specific headers for debugging
        cf_ip = request.headers.get('CF-Connecting-Ip')
        real_ip = request.headers.get('X-Real-Ip')
        forwarded_for = request.headers.get('X-Forwarded-For')
        current_app.logger.info(f"CF-Connecting-Ip: {cf_ip}")
        current_app.logger.info(f"X-Real-Ip: {real_ip}")
        current_app.logger.info(f"X-Forwarded-For: {forwarded_for}")
        current_app.logger.info(f"Remote addr: {request.remote_addr}")
        
        if not is_ip_allowed(client_ip):
            # Log the attempt but don't expose super admin existence
            current_app.logger.warning(f"Unauthorized access attempt from IP: {client_ip}")
            # Return 404 instead of 403 to hide super admin existence
            abort(404)
        
        # Check if super admin is authenticated
        if not session.get('super_admin_authenticated'):
            return redirect(url_for('superadmin.login'))
        
        # Verify session token
        session_token = session.get('super_admin_token')
        session_username = session.get('super_admin_username')
        session_timestamp = session.get('super_admin_timestamp')
        
        if not all([session_token, session_username, session_timestamp]):
            session.clear()
            return redirect(url_for('superadmin.login'))
        
        # Check token expiry (30 minutes)
        current_time = int(time.time())
        if current_time - session_timestamp > 1800:  # 30 minutes
            session.clear()
            return redirect(url_for('superadmin.login'))
        
        # Verify token
        if not verify_super_admin_token(session_token, session_username, session_timestamp):
            session.clear()
            return redirect(url_for('superadmin.login'))
        
        # Log access for security audit
        current_app.logger.info(f"Super admin access: {session_username} from IP: {client_ip}")
        
        return f(*args, **kwargs)
    
    return decorated_function

def rate_limit_super_admin(f):
    """Rate limiting decorator for super admin endpoints - DISABLED for whitelisted IPs"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip rate limiting for whitelisted IPs
        return f(*args, **kwargs)
    
    return decorated_function 