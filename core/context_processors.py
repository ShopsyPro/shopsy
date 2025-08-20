from datetime import datetime
from flask import session, current_app
from models import Shop
import logging

logger = logging.getLogger(__name__)

def register_context_processors(app):
    """Register all context processors with the Flask app"""
    
    @app.context_processor
    def inject_user_shop():
        """Make current user's shop data available to all templates"""
        if 'user_id' in session:
            try:
                current_shop = Shop.get_by_id(session['user_id'])
                if current_shop:
                    return {
                        'current_shop': current_shop,
                        'current_avatar_url': current_shop.get('avatar_url', '/static/assets/default_avatar.png'),
                        'current_shop_name': current_shop.get('name', ''),
                        'current_shop_description': current_shop.get('description', 'Welcome to our digital marketplace!')
                    }
            except Exception as e:
                # Log error but don't break the app
                logger.error(f"Error in context processor: {str(e)}")
        
        return {
            'current_shop': None,
            'current_avatar_url': '/static/assets/default_avatar.png',
            'current_shop_name': '',
            'current_shop_description': 'Welcome to our digital marketplace!'
        }

    @app.context_processor
    def inject_now():
        """Make current datetime available to templates"""
        return {'now': datetime.utcnow()}
    
    @app.context_processor
    def inject_config():
        """Make config values available to templates"""
        return {'config': current_app.config} 