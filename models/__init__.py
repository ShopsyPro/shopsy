"""
Models package initialization file that imports and exports all model classes.
This ensures all existing imports continue to work after the refactoring.
"""

# Import base database connection (keep available for backward compatibility)
from .base import db, ObjectId, datetime, timedelta

# Import all model classes
from .shop import Shop
from .cart import Cart
from .order import Order
from .customer import CustomerOTP, CustomerOrderTracker
from .activity import ActivityLog
from .subscription import Subscription

# Export all models so they can be imported from the models package
__all__ = [
    # Database utilities
    'db', 'ObjectId', 'datetime', 'timedelta',
    
    # Model classes
    'Shop', 'Cart', 'Order', 
    'CustomerOTP', 'CustomerOrderTracker', 'ActivityLog', 'Subscription'
] 