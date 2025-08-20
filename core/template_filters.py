from datetime import datetime
from models import Order

def register_filters(app):
    """Register all custom template filters with the Flask app"""
    
    @app.template_filter('order_display_id')
    def order_display_id_filter(order):
        """Template filter to get display ID for an order"""
        return Order.get_display_id(order)

    @app.template_filter('short_display_id')
    def short_display_id_filter(order):
        """Template filter to get short display ID for an order"""
        return Order.get_short_display_id(order)

    @app.template_filter('activity_color')
    def activity_color_filter(action_type):
        colors = {
            'create': 'green',
            'update': 'yellow',
            'delete': 'red',
            'order': 'blue'
        }
        return colors.get(action_type.lower(), 'purple')

    @app.template_filter('activity_icon')
    def activity_icon_filter(item_type):
        icons = {
            'product': 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4',
            'category': 'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z',
            'coupon': 'M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z',
            'order': 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'
        }
        return icons.get(item_type.lower(), 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z')

    @app.template_filter('time_ago')
    def time_ago_filter(timestamp):
        now = datetime.utcnow()
        diff = now - timestamp
        
        minutes = diff.seconds // 60
        hours = minutes // 60
        days = diff.days
        
        if days > 0:
            return f"{days} day{'s' if days > 1 else ''} ago"
        elif hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif minutes > 0:
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    @app.template_filter('format_datetime')
    def format_datetime_filter(timestamp, format_string='%b %d, %Y %H:%M:%S'):
        """Safely format a datetime with a fallback for invalid timestamps"""
        if not timestamp:
            return ""
        
        try:
            return timestamp.strftime(format_string)
        except (ValueError, AttributeError, TypeError):
            # Handle various errors
            return "" 