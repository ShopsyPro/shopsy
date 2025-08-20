import os
from flask import Flask, session, request, g, render_template
from datetime import datetime, timedelta
import time
import logging
import sys

# Import configuration
from config import config

# Import core modules
from core.template_filters import register_filters
from core.context_processors import register_context_processors

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.products import products_bp
from blueprints.categories import categories_bp
from blueprints.coupons import coupons_bp
from blueprints.shop import shop_bp
from blueprints.cart import cart_bp
from blueprints.orders import orders_bp
from blueprints.privacy import privacy
from blueprints.terms import terms
from blueprints.support import support
from blueprints.payments import payments_bp
from blueprints.superadmin import superadmin_bp
from blueprints.subscriptions import subscriptions_bp

# Import models
from models import Shop
from models.order import Order

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # This will output to systemd/journalctl
        logging.FileHandler('logs/app.log', mode='a')  # Also log to file
    ]
)
logger = logging.getLogger(__name__)

def create_app(config_name=None):
    """Application factory pattern"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__, static_folder='static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Add min and max functions and models to Jinja environment
    app.jinja_env.globals.update(min=min, max=max, Shop=Shop, Order=Order)
    
    # Register template filters and context processors
    register_filters(app)
    register_context_processors(app)
    
    # Make sure all sessions are permanent
    @app.before_request
    def make_session_permanent():
        session.permanent = True
        
        # If user is authenticated, refresh their session and update online status
        if 'user_id' in session:
            # Check at most once per minute (to avoid constant database hits)
            last_check = session.get('last_check_timestamp', 0)
            now = int(datetime.utcnow().timestamp())
            
            # Only check once per minute to reduce database load
            if now - last_check > 60:
                # Update the check timestamp
                session['last_check_timestamp'] = now
                
                # Verify user still exists (once per minute)
                user = Shop.get_by_id(session['user_id'])
                if not user:
                    # User no longer exists, clear session
                    session.clear()
                else:
                    # Update online status for active users
                    Shop.update_online_status(session['user_id'])
        
        # Always mark the session as modified to refresh expiry
        session.modified = True
    
    # Performance monitoring middleware
    @app.before_request
    def start_timer():
        g.start = time.time()
    
    @app.after_request
    def log_request(response):
        if hasattr(g, 'start'):
            duration = time.time() - g.start
            if duration > 1.0:  # Log slow requests (>1 second)
                logger.warning(f"Slow request: {request.endpoint} took {duration:.2f}s")
            elif duration > 0.5:  # Log moderately slow requests (>0.5 seconds)
                logger.info(f"Moderate request: {request.endpoint} took {duration:.2f}s")
        
        # Add cache control headers for authenticated pages
        if 'user_id' in session or request.endpoint in ['orders.customer_orders_dashboard', 'orders.customer_orders_support_page', 'orders.customer_tickets_page', 'orders.track_orders']:
            # Prevent caching of authenticated pages
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            # Add unique timestamp to prevent back/forward navigation issues
            response.headers['X-Timestamp'] = str(int(time.time()))
        
        return response
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(coupons_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(privacy)
    app.register_blueprint(terms)
    app.register_blueprint(support)
    app.register_blueprint(payments_bp)
    app.register_blueprint(superadmin_bp)
    app.register_blueprint(subscriptions_bp)
    
    # Initialize background tasks for superadmin
    from blueprints.superadmin.routes import init_background_tasks
    init_background_tasks(app)
    
    # Initialize subscription scheduler (temporarily disabled for debugging)
    # from core.scheduler import init_scheduler
    # init_scheduler(app)
    
    # Public pages routes
    @app.route('/cryptocurrencies')
    def cryptocurrencies():
        """Display supported cryptocurrencies page"""
        return render_template('_base/cryptocurrencies.html')
    
    # Register 404 error handler
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error/404.html'), 404
    
    return app

# Create the application instance
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)