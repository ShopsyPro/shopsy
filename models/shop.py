"""
Shop model for handling shop-related operations.
"""

from .base import (
    db, ObjectId, datetime, timedelta, generate_password_hash, 
    check_password_hash, uuid, re, time, hashlib, random, string
)

class Shop:
    collection = db.shops
    
    @staticmethod
    def create(username, email, password, shop_name):
        """Create a new shop with owner user details"""
        # Import here to avoid circular imports
        from core.username_validator import is_reserved_username, get_reserved_username_message
        
        # Check if username is reserved
        if is_reserved_username(username):
            raise ValueError(get_reserved_username_message())
        
        # Check if username already exists
        if Shop.get_by_username(username):
            raise ValueError(f"Username '{username}' already exists")
        
        # Check if email already exists
        if Shop.get_by_email(email):
            raise ValueError(f"Email '{email}' already exists")
        
        # Generate unique merchant code automatically
        merchant_code = Shop.generate_merchant_code(username)
        
        shop = {
            "owner": {
                "username": username.lower(),
                "email": email.lower(),
                "password_hash": generate_password_hash(password, method='pbkdf2:sha256'),
                "created_at": datetime.utcnow()
            },
            "name": shop_name,
            "merchant_code": merchant_code,  # Auto-assigned unique merchant code
            "avatar_url": None,  # Shop owner's avatar URL (S3)
            "description": "Welcome to our digital marketplace!",  # Shop description
            "is_paid": False,  # Default to free plan
            "selected_theme": "classic",  # Theme selection (classic, dark-elegance, bold-minimalist)
            "categories": [],
            "products": [],
            "coupons": [],
            "crypto_addresses": {
                "btc": "",
                "eth": "",
                "ltc": "",
                "bch": "",
                "usdt": "",
                "usdc": "",
                "dai": "",
                "sol": "",
                "bnb": "",
                "trx": "",
                "doge": "",
                "shib": "",
                "link": "",
                "uni": "",
                "aave": ""
            },
            "login_tracking": {
                "last_login": None,
                "login_ips": [],  # Array to store all IP addresses used for login
                "online_status": "offline"  # online/offline status
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "activity_log": []
        }
        
        result = Shop.collection.insert_one(shop)
        shop["_id"] = result.inserted_id
        return shop
    
    @staticmethod
    def get_by_id(shop_id):
        """Get a shop by ID"""
        return Shop.collection.find_one({"_id": ObjectId(shop_id)})
    
    @staticmethod
    def get_by_username(username):
        """Get a shop by owner username"""
        return Shop.collection.find_one({"owner.username": username.lower()})
    
    @staticmethod
    def get_by_email(email):
        """Get a shop by owner email"""
        return Shop.collection.find_one({"owner.email": email.lower()})
    
    @staticmethod
    def check_password(shop_id, password):
        """Check if password is correct"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            return check_password_hash(shop["owner"]["password_hash"], password)
        return False
    
    @staticmethod
    def update_owner(shop_id, **kwargs):
        """Update shop owner details"""
        update_fields = {}
        
        # Hash password if provided
        if "password" in kwargs:
            update_fields["owner.password_hash"] = generate_password_hash(kwargs["password"], method='pbkdf2:sha256')
            del kwargs["password"]
        
        # Map other fields to the owner subdocument
        for key, value in kwargs.items():
            if key not in ["username"]:  # Don't allow updating username
                update_fields[f"owner.{key}"] = value
        
        update_fields["updated_at"] = datetime.utcnow()
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {"$set": update_fields}
        )
        return Shop.get_by_id(shop_id)
    
    @staticmethod
    def update_shop(shop_id, **kwargs):
        """Update shop details"""
        kwargs["updated_at"] = datetime.utcnow()
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {"$set": kwargs}
        )
        return Shop.get_by_id(shop_id)
    
    # Category methods
    @staticmethod
    def add_category(shop_id, name, description=None):
        """Add a new category to the shop"""
        # Validate category name
        if not isinstance(name, str):
            raise ValueError("Category name must be a string")
        
        if len(name.strip()) == 0:
            raise ValueError("Category name cannot be empty")
        
        if len(name.strip()) > 32:
            raise ValueError("Category name cannot exceed 32 characters")
        
        # Clean the name
        name = name.strip()
        
        # Check if category with this name already exists
        shop = Shop.get_by_id(shop_id)
        if shop and any(cat["name"].lower() == name.lower() for cat in shop.get("categories", [])):
            raise ValueError(f"A category with name '{name}' already exists")
        
        category = {
            "_id": ObjectId(),  # Generate new ObjectId for the category
            "name": name,
            "description": description,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$push": {"categories": category},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Log the activity
        Shop.log_activity(shop_id, "create", "category", str(category["_id"]), f"Added category: {name}")
        
        return category
    
    @staticmethod
    def get_categories(shop_id):
        """Get all categories for a shop"""
        shop = Shop.get_by_id(shop_id)
        return shop.get("categories", []) if shop else []
    
    @staticmethod
    def get_category(shop_id, category_id):
        """Get a specific category by ID"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            for category in shop.get("categories", []):
                if str(category["_id"]) == str(category_id):
                    return category
        return None
    
    @staticmethod
    def update_category(shop_id, category_id, **kwargs):
        """Update a category"""
        # Validate category name if it's being updated
        if 'name' in kwargs:
            name = kwargs['name']
            if not isinstance(name, str):
                raise ValueError("Category name must be a string")
            
            if len(name.strip()) == 0:
                raise ValueError("Category name cannot be empty")
            
            if len(name.strip()) > 32:
                raise ValueError("Category name cannot exceed 32 characters")
            
            # Clean the name
            kwargs['name'] = name.strip()
            
            # Check if the new name conflicts with existing categories (excluding current category)
            shop = Shop.get_by_id(shop_id)
            if shop:
                for category in shop.get("categories", []):
                    if (str(category["_id"]) != str(category_id) and 
                        category["name"].lower() == kwargs['name'].lower()):
                        raise ValueError(f"A category with name '{kwargs['name']}' already exists")
        
        for key, value in kwargs.items():
            update_field = f"categories.$.{key}"
            
            Shop.collection.update_one(
                {
                    "_id": ObjectId(shop_id),
                    "categories._id": ObjectId(category_id)
                },
                {
                    "$set": {
                        update_field: value,
                        "categories.$.updated_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        
        # Log the activity
        Shop.log_activity(shop_id, "update", "category", category_id, f"Updated category: {kwargs.get('name', 'unknown')}")
        
        shop = Shop.get_by_id(shop_id)
        if shop:
            for category in shop.get("categories", []):
                if str(category["_id"]) == str(category_id):
                    return category
        return None
    
    @staticmethod
    def delete_category(shop_id, category_id):
        """Delete a category"""
        # First get the category to log its name
        category = Shop.get_category(shop_id, category_id)
        
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$pull": {"categories": {"_id": ObjectId(category_id)}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Also update any products that use this category to set category_id to null
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$set": {
                    "products.$[elem].category_id": None,
                    "updated_at": datetime.utcnow()
                }
            },
            array_filters=[{"elem.category_id": str(category_id)}]
        )
        
        # Also update any coupons that reference this category to set category_id to null
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$set": {
                    "coupons.$[elem].category_id": None,
                    "updated_at": datetime.utcnow()
                }
            },
            array_filters=[{"elem.category_id": str(category_id)}]
        )
        
        # Log the activity
        if category:
            Shop.log_activity(shop_id, "delete", "category", category_id, f"Deleted category: {category.get('name', 'unknown')}")
        
        return result.modified_count > 0
    
    # Product methods
    @staticmethod
    def add_product(shop_id, name, price, category_id=None, image_url=None, description=None, stock=0, stock_values=None, stock_delimiter='|', status="Active", pricing_options=None, infinite_stock=False, is_visible=True):
        """Add a new product to the shop"""
        # Enforce: For infinite stock, exactly one stock value must be provided
        if infinite_stock:
            # Check if this is a duration pricing product
            if pricing_options and len(pricing_options) > 0:
                # For duration pricing, check each option has exactly one stock value
                for i, option in enumerate(pricing_options):
                    option_stock_values = option.get('stock_values', [])
                    if not option_stock_values or len(option_stock_values) != 1 or not option_stock_values[0].strip():
                        raise ValueError(f"Infinite stock products with duration pricing require exactly one product value/group link per option. Option '{option.get('name', f'#{i+1}')}' has {len(option_stock_values) if option_stock_values else 0} values.")
            else:
                # For regular infinite stock products, check main stock_values
                if not stock_values or len(stock_values) != 1 or not stock_values[0].strip():
                    raise ValueError("Infinite stock products require exactly one product value/group link.")
        # If pricing options are provided, update each option to include stock
        if pricing_options and len(pricing_options) > 0:
            # If we have pricing options but no stock values included, use the base stock for all
            has_stock_values = any('stock_values' in option for option in pricing_options)
            if not has_stock_values:
                for option in pricing_options:
                    option['stock'] = int(stock)
                    option['stock_values'] = stock_values or []
                    option['stock_delimiter'] = stock_delimiter
        
        # Ensure stock values are unique to prevent duplicate deliveries
        if stock_values:
            unique_values = list(dict.fromkeys(stock_values))  # Preserves order while removing duplicates
            if len(unique_values) != len(stock_values):
                duplicate_count = len(stock_values) - len(unique_values)
                print(f"Warning: Removed {duplicate_count} duplicate stock values for product {name}")
                stock_values = unique_values
        
        product = {
            "_id": ObjectId(),  # Generate new ObjectId for the product
            "name": name,
            "price": float(price),
            "category_id": str(category_id) if category_id else None,
            "image_url": image_url,
            "description": description,
            "stock": int(stock),  # This becomes the calculated stock count
            "stock_values": stock_values or [],  # Array of actual values to deliver
            "stock_delimiter": stock_delimiter,  # Delimiter used for parsing
            "infinite_stock": infinite_stock,  # Whether this product has infinite stock
            "status": status,
            "is_visible": is_visible,  # Whether this product is visible on storefront
            "has_duration_pricing": pricing_options is not None and len(pricing_options) > 0,
            "pricing_options": pricing_options or [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$push": {"products": product},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Log the activity
        Shop.log_activity(shop_id, "create", "product", str(product["_id"]), f"Added product: {name}")
        
        return product
    
    @staticmethod
    def get_products(shop_id):
        """Get all products for a shop"""
        shop = Shop.get_by_id(shop_id)
        return shop.get("products", []) if shop else []
    
    @staticmethod
    def get_product(shop_id, product_id):
        """Get a specific product by ID"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            for product in shop.get("products", []):
                if str(product["_id"]) == str(product_id):
                    return product
        return None
    
    @staticmethod
    def get_products_by_ids(shop_id, product_ids):
        """Get multiple products by IDs in a single query - eliminates N+1 problem"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return {}
        
        # Convert product_ids to strings for comparison
        product_id_set = {str(pid) for pid in product_ids}
        
        # Filter products efficiently
        products = {}
        for product in shop.get("products", []):
            if str(product["_id"]) in product_id_set:
                products[str(product["_id"])] = product
        
        return products
    
    @staticmethod
    def get_products_by_category(shop_id, category_id):
        """Get products by category ID"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            return [p for p in shop.get("products", []) if p.get("category_id") == str(category_id)]
        return []
    
    @staticmethod
    def update_product(shop_id, product_id, **kwargs):
        """Update a product"""
        # Handle special case for pricing_options
        if 'pricing_options' in kwargs:
            pricing_options = kwargs['pricing_options']
            kwargs['has_duration_pricing'] = len(pricing_options) > 0
            
            # Ensure each option has the required fields
            for i, option in enumerate(pricing_options):
                if 'name' not in option or 'price' not in option:
                    raise ValueError(f"Option {i+1} is missing required name or price")
                    
                # Make sure price is a float
                if 'price' in option:
                    option['price'] = float(option['price'])
                    
                # Make sure stock is an integer and handle stock values
                if 'stock' in option:
                    option['stock'] = int(option['stock'])
                else:
                    option['stock'] = 0
                
                # Ensure stock_values and delimiter are present
                if 'stock_values' not in option:
                    option['stock_values'] = []
                if 'stock_delimiter' not in option:
                    option['stock_delimiter'] = kwargs.get('stock_delimiter', '|')
                    
            # Optional validation: Check for duplicate option names
            option_names = [opt.get('name') for opt in pricing_options]
            if len(option_names) != len(set(option_names)):
                raise ValueError("Duplicate option names are not allowed")
        
        # Handle stock values for main product
        if 'stock_values' in kwargs and isinstance(kwargs['stock_values'], list):
            # Ensure stock values are unique to prevent duplicate deliveries
            stock_values = kwargs['stock_values']
            unique_values = list(dict.fromkeys(stock_values))  # Preserves order while removing duplicates
            if len(unique_values) != len(stock_values):
                duplicate_count = len(stock_values) - len(unique_values)
                print(f"Warning: Removed {duplicate_count} duplicate stock values during product update")
                kwargs['stock_values'] = unique_values
            
            # Enforce: For infinite stock, exactly one stock value must be provided
            if kwargs.get('infinite_stock', False):
                # Check if this is a duration pricing product
                pricing_options = kwargs.get('pricing_options', [])
                if pricing_options and len(pricing_options) > 0:
                    # For duration pricing, check each option has exactly one stock value
                    for i, option in enumerate(pricing_options):
                        option_stock_values = option.get('stock_values', [])
                        if not option_stock_values or len(option_stock_values) != 1 or not option_stock_values[0].strip():
                            raise ValueError(f"Infinite stock products with duration pricing require exactly one product value/group link per option. Option '{option.get('name', f'#{i+1}')}' has {len(option_stock_values) if option_stock_values else 0} values.")
                else:
                    # For regular infinite stock products, check main stock_values
                    stock_values = kwargs.get('stock_values', [])
                    if not stock_values or len(stock_values) != 1 or not stock_values[0].strip():
                        raise ValueError("Infinite stock products require exactly one product value/group link.")
                kwargs['stock'] = 999999  # Set high number for infinite stock
            else:
                kwargs['stock'] = len(kwargs['stock_values'])
        
        # Set updated timestamp
        kwargs['updated_at'] = datetime.utcnow()
        
        # Build update query
        update_fields = {}
        for key, value in kwargs.items():
            update_fields[f"products.$.{key}"] = value
            
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id), "products._id": ObjectId(product_id)},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            raise ValueError("Product not found")
        
        # Log the activity
        Shop.log_activity(shop_id, "update", "product", str(product_id), f"Updated product")
        
        # Return the updated product
        return Shop.get_product(shop_id, product_id)
    
    @staticmethod
    def delete_product(shop_id, product_id):
        """Delete a product"""
        # First get the product to log its name
        product = Shop.get_product(shop_id, product_id)
        
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$pull": {"products": {"_id": ObjectId(product_id)}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Log the activity
        if product:
            Shop.log_activity(shop_id, "delete", "product", product_id, f"Deleted product: {product.get('name', 'unknown')}")
        
        return result.modified_count > 0
    
    # Coupon methods
    @staticmethod
    def add_coupon(shop_id, code, coupon_type, discount_value, expiry_date, category_id=None, is_public=False, max_cap=None, min_order_value=None):
        """Add a new coupon to the shop"""
        coupon = {
            "_id": ObjectId(),  # Generate new ObjectId for the coupon
            "code": code.upper(),
            "type": coupon_type,  # 'percentage' or 'fixed'
            "discount_value": float(discount_value),  # Can be percentage or fixed amount
            "expiry_date": datetime.strptime(expiry_date, "%Y-%m-%d") if isinstance(expiry_date, str) else expiry_date,
            "category_id": str(category_id) if category_id else None,
            "status": "Active",
            "is_public": bool(is_public),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Add max_cap for percentage coupons
        if coupon_type == 'percentage' and max_cap is not None:
            coupon["max_cap"] = float(max_cap)
        
        # Add minimum order value for fixed coupons
        if coupon_type == 'fixed' and min_order_value is not None:
            coupon["min_order_value"] = float(min_order_value)
        
        # Keep backward compatibility with discount_percentage field
        if coupon_type == 'percentage':
            coupon["discount_percentage"] = float(discount_value)  # Changed from int to float
        else:
            coupon["discount_percentage"] = 0  # For backward compatibility
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$push": {"coupons": coupon},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Log the activity
        Shop.log_activity(shop_id, "create", "coupon", str(coupon["_id"]), f"Added coupon: {code}")
        
        return coupon
    
    @staticmethod
    def get_coupons(shop_id):
        """Get all coupons for a shop"""
        shop = Shop.get_by_id(shop_id)
        return shop.get("coupons", []) if shop else []
    
    @staticmethod
    def get_coupon(shop_id, coupon_id):
        """Get a specific coupon by ID"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            for coupon in shop.get("coupons", []):
                if str(coupon["_id"]) == str(coupon_id):
                    return coupon
        return None
    
    @staticmethod
    def get_coupon_by_code(shop_id, code):
        """Get a coupon by code"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            for coupon in shop.get("coupons", []):
                if coupon["code"] == code.upper():
                    return coupon
        return None
    
    @staticmethod
    def update_coupon(shop_id, coupon_id, **kwargs):
        """Update a coupon"""
        # Handle date conversion
        if 'expiry_date' in kwargs and isinstance(kwargs['expiry_date'], str):
            kwargs['expiry_date'] = datetime.strptime(kwargs['expiry_date'], "%Y-%m-%d")
        
        for key, value in kwargs.items():
            update_field = f"coupons.$.{key}"
            
            Shop.collection.update_one(
                {
                    "_id": ObjectId(shop_id),
                    "coupons._id": ObjectId(coupon_id)
                },
                {
                    "$set": {
                        update_field: value,
                        "coupons.$.updated_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        
        # Log the activity
        Shop.log_activity(shop_id, "update", "coupon", coupon_id, f"Updated coupon: {kwargs.get('code', 'unknown')}")
        
        shop = Shop.get_by_id(shop_id)
        if shop:
            for coupon in shop.get("coupons", []):
                if str(coupon["_id"]) == str(coupon_id):
                    return coupon
        return None
    
    @staticmethod
    def get_coupon_usage_count(shop_id, coupon_id):
        """Get the usage count of a coupon based on completed orders"""
        # Import here to avoid circular import
        from .order import Order
        
        # Query the orders collection for completed orders with this coupon
        pipeline = [
            {
                "$match": {
                    "shop_id": ObjectId(shop_id),
                    "status": "completed",
                    "coupon.coupon_id": str(coupon_id)
                }
            },
            {
                "$count": "usage_count"
            }
        ]
        
        result = list(Order.collection.aggregate(pipeline))
        if result and len(result) > 0:
            return result[0].get("usage_count", 0)
        return 0
    
    @staticmethod
    def get_all_coupon_usage_counts(shop_id):
        """Get usage counts for all coupons in a shop in a single query"""
        # Import here to avoid circular import
        from .order import Order
        
        # Query the orders collection for all completed orders with coupons
        pipeline = [
            {
                "$match": {
                    "shop_id": ObjectId(shop_id),
                    "status": "completed",
                    "coupon.coupon_id": {"$exists": True, "$ne": None}
                }
            },
            {
                "$group": {
                    "_id": "$coupon.coupon_id",
                    "usage_count": {"$sum": 1}
                }
            }
        ]
        
        result = list(Order.collection.aggregate(pipeline))
        
        # Convert to dictionary for easy lookup
        usage_counts = {}
        for item in result:
            usage_counts[item["_id"]] = item["usage_count"]
        
        return usage_counts
    
    @staticmethod
    def delete_coupon(shop_id, coupon_id):
        """Delete a coupon"""
        # First get the coupon to log its code
        coupon = Shop.get_coupon(shop_id, coupon_id)
        
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$pull": {"coupons": {"_id": ObjectId(coupon_id)}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Log the activity
        if coupon:
            Shop.log_activity(shop_id, "delete", "coupon", coupon_id, f"Deleted coupon: {coupon.get('code', 'unknown')}")
        
        return result.modified_count > 0
    
    # Activity Log methods
    @staticmethod
    def log_activity(shop_id, action_type, item_type, item_id=None, details=None):
        """Log an activity in the shop"""
        print(f"Logging activity: {action_type} {item_type} for shop {shop_id} - {details}")
        
        # Ensure shop_id is properly handled
        if not isinstance(shop_id, ObjectId):
            try:
                shop_id = ObjectId(shop_id)
            except Exception as e:
                print(f"Error converting shop_id to ObjectId: {e}")
                return None
                
        activity = {
            "_id": ObjectId(),  # Generate new ObjectId for the activity
            "action_type": action_type,
            "item_type": item_type,
            "item_id": item_id,
            "details": details,
            "timestamp": datetime.utcnow()
        }
        
        try:
            # Make sure the shop has an activity_log array
            Shop.collection.update_one(
                {"_id": shop_id, "activity_log": {"$exists": False}},
                {"$set": {"activity_log": []}}
            )
            
            # Now add the activity with log rotation to prevent unbounded growth
            result = Shop.collection.update_one(
                {"_id": shop_id},
                {
                    "$push": {
                        "activity_log": {
                            "$each": [activity],
                            "$slice": -1000  # Keep only last 1000 activities
                        }
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            print(f"Activity log updated: {result.modified_count} document(s) modified")
            return activity
            
        except Exception as e:
            print(f"Error logging activity: {e}")
            return None
    
    @staticmethod
    def get_recent_activities(shop_id, hours=24):
        """Get recent activities for a shop from the last specified hours"""
        # Get the shop document
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return []
        
        # Get activities from shop's activity_log array
        all_activities = shop.get("activity_log", [])
        
        if not all_activities:
            return []
        
        # Calculate the time threshold for recent activities
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        
        # Filter activities by time and sort by timestamp (newest first)
        recent_activities = [
            activity for activity in all_activities
            if activity.get('timestamp') and activity['timestamp'] >= time_threshold
        ]
        
        # Filter out order creation activities for unpaid orders
        filtered_activities = []
        for activity in recent_activities:
            if activity.get('action_type') == 'create' and activity.get('item_type') == 'order':
                # For order creation activities, check if the order is completed
                from .order import Order
                order_id = activity.get('item_id')
                if order_id:
                    try:
                        order = Order.get_by_id(order_id)
                        if order and order.get('status') == 'completed':
                            filtered_activities.append(activity)
                    except:
                        # If order not found or error, skip this activity
                        continue
            else:
                # Include all non-order activities
                filtered_activities.append(activity)
        
        # Sort by timestamp (newest first)
        filtered_activities.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)
        
        return filtered_activities
    
    # Analytics methods
    @staticmethod
    def get_revenue_by_timeframe(shop_id, days):
        """Get revenue data for a specific timeframe"""
        # Import here to avoid circular import
        from .order import Order
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Use the separate orders collection for better performance and accuracy
        pipeline = [
            {"$match": {
                "shop_id": ObjectId(shop_id),
                "status": "completed",
                "created_at": {"$gte": start_date, "$lte": end_date}
            }},
            {"$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"},
                    "day": {"$dayOfMonth": "$created_at"}
                },
                "total": {"$sum": "$total_amount"},
                "count": {"$sum": 1},
                "date": {"$first": "$created_at"}
            }},
            {"$sort": {"date": 1}}
        ]
        
        result = list(Order.collection.aggregate(pipeline))
        
        # Convert the result to the format expected by the chart
        formatted_results = []
        for item in result:
            date_obj = item.get('date')
            formatted_date = date_obj.strftime('%Y-%m-%d')
            formatted_results.append({
                'date': formatted_date,
                'total': item.get('total', 0),
                'count': item.get('count', 0)
            })
            
        # If no data, return empty list
        if not formatted_results:
            return []
            
        # Fill in missing dates with zero values - handle all timeframes appropriately
        date_range = []
        current_date = start_date
        
        # Ensure we generate one entry per day for all timeframes
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            date_range.append(date_str)
            current_date += timedelta(days=1)
            
        complete_results = []
        for date_str in date_range:
            existing_entry = next((item for item in formatted_results if item['date'] == date_str), None)
            if existing_entry:
                complete_results.append(existing_entry)
            else:
                complete_results.append({
                    'date': date_str,
                    'total': 0,
                    'count': 0
                })
                
        return complete_results

    @staticmethod
    def generate_merchant_code(username=None):
        """Generate a unique 5-character alphanumeric merchant code starting with a letter"""
        import random
        import string
        
        chars = string.ascii_uppercase + string.digits
        first_char = string.ascii_uppercase  # Must start with a letter
        
        for _ in range(1000):  # Try up to 1000 times to avoid infinite loop
            code = random.choice(first_char) + ''.join(random.choices(chars, k=4))
            existing = Shop.collection.find_one({"merchant_code": code})
            if not existing:
                return code
        
        raise Exception("Unable to generate unique merchant code after 1000 attempts.")
    
    @staticmethod
    def get_timestamp_hash():
        """Generate a compact timestamp hash (5 chars, base36)"""
        import time
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        timestamp = int(time.time())
        base36 = ''
        while timestamp > 0:
            base36 = chars[timestamp % 36] + base36
            timestamp //= 36
        return base36[-5:].zfill(5)
    
    @staticmethod
    def track_login(shop_id, ip_address):
        """Track a successful login attempt with enhanced IP tracking"""
        now = datetime.utcnow()
        
        # Get current shop data to check existing IPs
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return
        
        login_tracking = shop.get('login_tracking', {})
        login_ips = login_tracking.get('login_ips', [])
        
        # Check if this IP already exists
        ip_exists = False
        for ip_entry in login_ips:
            if isinstance(ip_entry, dict) and ip_entry.get('ip') == ip_address:
                # Update last used timestamp
                ip_entry['last_used'] = now
                ip_exists = True
                break
            elif isinstance(ip_entry, str) and ip_entry == ip_address:
                # Convert old string format to new dict format
                ip_entry = {
                    'ip': ip_address,
                    'first_used': now,
                    'last_used': now
                }
                ip_exists = True
                break
        
        if not ip_exists:
            # Add new IP entry
            new_ip_entry = {
                'ip': ip_address,
                'first_used': now,
                'last_used': now
            }
            login_ips.append(new_ip_entry)
        
        # Update last login and online status
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$set": {
                    "login_tracking.last_login": now,
                    "login_tracking.online_status": "online",
                    "login_tracking.login_ips": login_ips,
                    "updated_at": now
                }
            }
        )
        
        # Log the login activity
        Shop.log_activity(shop_id, "login", "session", None, "Login successful")
    
    @staticmethod
    def is_online(shop_id, timeout_minutes=15):
        """Check if a merchant is currently online based on last activity time"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return False
        
        # Get the most recent activity time (either last_login or updated_at)
        last_login = shop.get("login_tracking", {}).get("last_login")
        updated_at = shop.get("updated_at")
        
        # Use the more recent timestamp
        last_activity = None
        if last_login and updated_at:
            last_activity = max(last_login, updated_at)
        elif last_login:
            last_activity = last_login
        elif updated_at:
            last_activity = updated_at
        else:
            return False
        
        timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        return last_activity > timeout_threshold
    
    @staticmethod
    def get_online_status(shop_id, timeout_minutes=15):
        """Get the online status of a merchant"""
        is_online = Shop.is_online(shop_id, timeout_minutes)
        return "online" if is_online else "offline"
    
    @staticmethod
    def update_online_status(shop_id):
        """Update the online status based on last activity time"""
        is_online = Shop.is_online(shop_id)
        status = "online" if is_online else "offline"
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$set": {
                    "login_tracking.online_status": status,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return status
    
    @staticmethod
    def get_all_online_shops(timeout_minutes=15):
        """Get all shops that are currently online"""
        timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        # Find shops where either last_login or updated_at is within timeout
        online_shops = Shop.collection.find({
            "$or": [
                {"login_tracking.last_login": {"$gt": timeout_threshold}},
                {"updated_at": {"$gt": timeout_threshold}}
            ]
        }).sort("updated_at", -1)
        
        return list(online_shops)
    
    @staticmethod
    def get_all_shops_with_online_status():
        """Get all shops with their online status and last online message"""
        shops = Shop.collection.find().sort("updated_at", -1)
        shops_with_status = []
        
        for shop in shops:
            shop_data = shop.copy()
            shop_data['online_status'] = Shop.get_online_status(shop['_id'])
            shop_data['last_online_message'] = Shop.get_last_online_message(shop['_id'])
            shop_data['last_online_data'] = Shop.get_last_online_data(shop['_id'])
            shops_with_status.append(shop_data)
        
        return shops_with_status
    
    @staticmethod
    def get_shop_with_online_status(shop_id):
        """Get shop data with current online status"""
        shop = Shop.get_by_id(shop_id)
        if shop:
            shop["current_online_status"] = Shop.get_online_status(shop_id)
        return shop
    
    @staticmethod
    def get_last_online_message(shop_id):
        """Get formatted last online message with graduated messaging"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return "Never online"
        
        # Get the most recent activity time (either last_login or updated_at)
        last_login = shop.get("login_tracking", {}).get("last_login")
        updated_at = shop.get("updated_at")
        
        # Use the more recent timestamp
        last_activity = None
        if last_login and updated_at:
            last_activity = max(last_login, updated_at)
        elif last_login:
            last_activity = last_login
        elif updated_at:
            last_activity = updated_at
        else:
            return "Never online"
        
        now = datetime.utcnow()
        time_diff = now - last_activity
        
        # Convert to hours and days
        hours_ago = time_diff.total_seconds() / 3600
        days_ago = hours_ago / 24
        
        # Active / Recent (less than 12 hours)
        if hours_ago < 12:
            hours = int(hours_ago)
            if hours == 0:
                return "Online now"
            elif hours == 1:
                return "Last online 1 hour ago"
            else:
                return f"Last online {hours} hours ago"
        
        # Offline Threshold (12 hours to 7 days)
        elif hours_ago < 24:
            hours = int(hours_ago)
            return f"Offline – Last online {hours} hours ago"
        
        elif days_ago < 2:
            return "Offline – Last online 1 day ago"
        
        elif days_ago < 7:
            days = int(days_ago)
            return f"Offline – Last online {days} days ago"
        
        # Long-term offline (7 days or more)
        else:
            weeks_ago = int(days_ago / 7)
            if weeks_ago == 1:
                return "Offline since 1 week ago"
            else:
                return f"Offline since {weeks_ago} weeks ago"
    
    @staticmethod
    def get_last_online_data(shop_id):
        """Get detailed last online data for API responses"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return {
                "message": "Never online",
                "status": "never",
                "last_login": None,
                "last_activity": None,
                "hours_ago": None,
                "days_ago": None
            }
        
        # Get the most recent activity time (either last_login or updated_at)
        last_login = shop.get("login_tracking", {}).get("last_login")
        updated_at = shop.get("updated_at")
        
        # Use the more recent timestamp
        last_activity = None
        if last_login and updated_at:
            last_activity = max(last_login, updated_at)
        elif last_login:
            last_activity = last_login
        elif updated_at:
            last_activity = updated_at
        else:
            return {
                "message": "Never online",
                "status": "never",
                "last_login": None,
                "last_activity": None,
                "hours_ago": None,
                "days_ago": None
            }
        
        now = datetime.utcnow()
        time_diff = now - last_activity
        
        hours_ago = time_diff.total_seconds() / 3600
        days_ago = hours_ago / 24
        
        # Determine status category
        if hours_ago < 12:
            status = "recent"
        elif hours_ago < 24:
            status = "offline_hours"
        elif days_ago < 7:
            status = "offline_days"
        else:
            status = "offline_weeks"
        
        return {
            "message": Shop.get_last_online_message(shop_id),
            "status": status,
            "last_login": last_login,
            "last_activity": last_activity,
            "hours_ago": hours_ago,
            "days_ago": days_ago
        }
    
    @staticmethod
    def get_shops_by_online_category(category):
        """Get shops filtered by online status category"""
        shops = Shop.collection.find().sort("updated_at", -1)
        filtered_shops = []
        
        for shop in shops:
            last_online_data = Shop.get_last_online_data(shop['_id'])
            if last_online_data['status'] == category:
                shop_data = shop.copy()
                shop_data['online_status'] = Shop.get_online_status(shop['_id'])
                shop_data['last_online_message'] = Shop.get_last_online_message(shop['_id'])
                shop_data['last_online_data'] = last_online_data
                filtered_shops.append(shop_data)
        
        return filtered_shops
    
    @staticmethod
    def get_next_sequence_number(shop_id):
        """Get next sequence number for the shop (daily reset)"""
        # Import here to avoid circular import
        from .order import Order
        
        today = datetime.utcnow().strftime('%Y%m%d')
        
        # Count orders for this shop today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        order_count = Order.collection.count_documents({
            "shop_id": ObjectId(shop_id),
            "created_at": {"$gte": today_start}
        })
        
        return order_count + 1

    @staticmethod
    def update_payment_settings(shop_id, **kwargs):
        """Update shop crypto payment addresses for all 15 supported cryptocurrencies"""
        crypto_addresses = {
            "btc": kwargs.get("btc", ""),
            "eth": kwargs.get("eth", ""),
            "ltc": kwargs.get("ltc", ""),
            "bch": kwargs.get("bch", ""),
            "usdt": kwargs.get("usdt", ""),
            "usdc": kwargs.get("usdc", ""),
            "dai": kwargs.get("dai", ""),
            "sol": kwargs.get("sol", ""),
            "bnb": kwargs.get("bnb", ""),
            "trx": kwargs.get("trx", ""),
            "doge": kwargs.get("doge", ""),
            "shib": kwargs.get("shib", ""),
            "link": kwargs.get("link", ""),
            "uni": kwargs.get("uni", ""),
            "aave": kwargs.get("aave", "")
        }
        
        update_fields = {
            "crypto_addresses": crypto_addresses,
            "updated_at": datetime.utcnow()
        }
        
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {"$set": update_fields}
        )
        
        # Log the activity
        Shop.log_activity(shop_id, "update", "payment_settings", None, "Updated crypto payment addresses")
        
        return Shop.get_by_id(shop_id) 
    
    @staticmethod
    def migrate_crypto_addresses():
        """Migrate existing shops to use only the 15 supported cryptocurrencies"""
        # Define the new crypto addresses structure
        new_crypto_addresses = {
            "btc": "",
            "eth": "",
            "ltc": "",
            "bch": "",
            "usdt": "",
            "usdc": "",
            "dai": "",
            "sol": "",
            "bnb": "",
            "trx": "",
            "doge": "",
            "shib": "",
            "link": "",
            "uni": "",
            "aave": ""
        }
        
        # Get all shops
        shops = Shop.collection.find({})
        migrated_count = 0
        
        for shop in shops:
            current_addresses = shop.get('crypto_addresses', {})
            
            # Create new addresses dict with only supported cryptocurrencies
            updated_addresses = new_crypto_addresses.copy()
            
            # Preserve existing addresses for supported cryptocurrencies
            for crypto in new_crypto_addresses.keys():
                if crypto in current_addresses:
                    updated_addresses[crypto] = current_addresses[crypto]
            
            # Update the shop
            Shop.collection.update_one(
                {"_id": shop["_id"]},
                {
                    "$set": {
                        "crypto_addresses": updated_addresses,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            migrated_count += 1
        
        return migrated_count 
    
    @staticmethod
    def ban_shop(shop_id, reason, banned_by="superadmin"):
        """Ban a shop - prevents access to dashboard and hides shop front"""
        from bson import ObjectId
        
        ban_data = {
            "banned": True,
            "ban_reason": reason,
            "banned_by": banned_by,
            "banned_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {"$set": ban_data}
        )
        
        if result.modified_count > 0:
            # Log the ban action
            Shop.log_activity(shop_id, "ban", "shop", None, f"Shop banned by {banned_by}. Reason: {reason}")
            return True
        return False
    
    @staticmethod
    def unban_shop(shop_id, unbanned_by="superadmin"):
        """Unban a shop - restores access to dashboard and shop front"""
        from bson import ObjectId
        
        result = Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {"$unset": {
                "banned": "",
                "ban_reason": "",
                "banned_by": "",
                "banned_at": ""
            }, "$set": {
                "updated_at": datetime.utcnow()
            }}
        )
        
        if result.modified_count > 0:
            # Log the unban action
            Shop.log_activity(shop_id, "unban", "shop", None, f"Shop unbanned by {unbanned_by}")
            return True
        return False
    
    @staticmethod
    def is_banned(shop_id):
        """Check if a shop is banned"""
        shop = Shop.get_by_id(shop_id)
        return shop.get('banned', False) if shop else False
    
    @staticmethod
    def get_ban_info(shop_id):
        """Get ban information for a shop"""
        shop = Shop.get_by_id(shop_id)
        if shop and shop.get('banned'):
            return {
                "banned": True,
                "ban_reason": shop.get('ban_reason'),
                "banned_by": shop.get('banned_by'),
                "banned_at": shop.get('banned_at')
            }
        return {"banned": False}
    
    @staticmethod
    def get_all_banned_shops():
        """Get all banned shops"""
        return list(Shop.collection.find({"banned": True}).sort("banned_at", -1))
    
    # Theme management methods
    @staticmethod
    def get_available_themes():
        """Get list of available themes"""
        return ["classic", "dark-elegance", "bold-minimalist"]
    
    @staticmethod
    def get_premium_themes():
        """Get list of premium-only themes"""
        return ["dark-elegance", "bold-minimalist"]
    
    @staticmethod
    def get_theme(shop_id):
        """Get the selected theme for a shop"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return "classic"
        
        selected_theme = shop.get("selected_theme", "classic")
        
        # If shop is not premium, force classic theme
        if not shop.get("is_paid", False) and selected_theme in Shop.get_premium_themes():
            return "classic"
        
        # Validate theme exists
        if selected_theme not in Shop.get_available_themes():
            return "classic"
        
        return selected_theme
    
    @staticmethod
    def set_theme(shop_id, theme_name):
        """Set the theme for a shop"""
        shop = Shop.get_by_id(shop_id)
        if not shop:
            raise ValueError("Shop not found")
        
        # Validate theme exists
        if theme_name not in Shop.get_available_themes():
            raise ValueError(f"Invalid theme: {theme_name}")
        
        # Check if user can access premium themes
        if theme_name in Shop.get_premium_themes() and not shop.get("is_paid", False):
            raise ValueError("Premium themes are only available to Premium subscribers")
        
        # Update theme
        Shop.collection.update_one(
            {"_id": ObjectId(shop_id)},
            {
                "$set": {
                    "selected_theme": theme_name,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Log the activity
        Shop.log_activity(shop_id, "update", "theme", None, f"Changed theme to: {theme_name}")
        
        return Shop.get_by_id(shop_id) 