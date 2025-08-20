"""
Base module for all models containing common imports and MongoDB connection.
"""

from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import re
import time
import hashlib
import random
import string

# Load environment variables
load_dotenv()

# Connect to MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.shop_db_dev

# Create critical indexes for performance
def create_indexes():
    """Create database indexes for optimal query performance"""
    try:
        # Shop collection indexes
        db.shops.create_index("owner.username", unique=True)
        db.shops.create_index("owner.email", unique=True)
        db.shops.create_index("merchant_code", unique=True)
        db.shops.create_index("login_tracking.last_login")
        db.shops.create_index([("created_at", -1)], name="shops_created_at_desc")  # For superadmin sorting
        db.shops.create_index([("banned", 1)], name="shops_banned_status")  # For ban status queries
        
        # Cart collection indexes
        db.carts.create_index("session_id", unique=True)
        
        # Order collection indexes
        db.orders.create_index("shop_id")
        db.orders.create_index("session_id")
        db.orders.create_index("status")
        db.orders.create_index("created_at")
        db.orders.create_index([("shop_id", 1), ("status", 1)])
        db.orders.create_index([("shop_id", 1), ("created_at", -1)])
        db.orders.create_index([("status", 1), ("created_at", -1)])  # For expired order queries
        db.orders.create_index("customer_email")  # For customer stats
        db.orders.create_index([("status", 1), ("total_amount", 1)])  # For revenue queries
        
        # Additional compound indexes for superadmin performance
        db.orders.create_index([("status", 1), ("created_at", -1), ("total_amount", 1)], name="orders_status_created_amount")  # For revenue analytics
        db.orders.create_index([("shop_id", 1), ("status", 1), ("total_amount", 1)], name="orders_shop_status_amount")  # For shop revenue queries
        
        # Failed orders collection indexes
        db.failed_orders.create_index("shop_id")
        db.failed_orders.create_index("failed_at")
        db.failed_orders.create_index("customer_email")
        db.failed_orders.create_index("order_id")
        db.failed_orders.create_index("session_id")
        db.failed_orders.create_index([("shop_id", 1), ("failed_at", -1)])
        db.failed_orders.create_index([("failed_at", -1)])  # For sorting by failed date
        
        print("Database indexes created successfully")
    except Exception as e:
        print(f"Warning: Could not create all indexes: {e}")

# Create indexes on startup
create_indexes()

# Export all commonly used items for models
__all__ = [
    'db', 'ObjectId', 'datetime', 'timedelta', 'os', 'generate_password_hash',
    'check_password_hash', 'uuid', 're', 'time', 'hashlib', 'random', 'string'
] 
