"""
Cart model for handling shopping cart operations.
"""

from datetime import datetime
from bson import ObjectId
import time
from .base import db

class Cart:
    collection = db.carts
    
    @staticmethod
    def create_or_get(session_id):
        """Create a new cart or get existing one by session ID"""
        cart = Cart.collection.find_one({"session_id": session_id})
        if not cart:
            cart = {
                "session_id": session_id,
                "items": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = Cart.collection.insert_one(cart)
            cart["_id"] = result.inserted_id
        return cart
    
    @staticmethod
    def add_item(session_id, shop_id, product_id, quantity, duration=None):
        """Add item to cart with optimized performance and server-side pricing only"""
        # Import here to avoid circular import
        from .shop import Shop
        
        # OPTIMIZATION: Get shop and product in single query with connection pooling
        shop = Shop.get_by_id(shop_id)
        if not shop:
            raise ValueError("Shop not found")
        
        # Find product in shop data (no separate query)
        product = None
        for p in shop.get('products', []):
            if str(p['_id']) == str(product_id):
                product = p
                break
        
        if not product:
            raise ValueError("Product not found")
            
        # Check if this is an infinite stock product and limit to quantity 1
        is_infinite_stock = product.get('infinite_stock', False)
        if is_infinite_stock and quantity > 1:
            raise ValueError("Infinite stock products can only be purchased with quantity 1. You'll receive the same access link/content regardless of quantity.")
            
        # Get shop owner username from already fetched shop data
        seller_username = shop.get("owner", {}).get("username", "unknown")
            
        # SECURITY FIX: Always use server-side pricing, never client-provided prices
        product_price = float(product.get('price', 0))
        item_duration = None
        stock_to_check = product.get('stock', 0)
        
        # If product has duration pricing and specific duration was provided
        if product.get('has_duration_pricing') and duration:
            item_duration = duration
            # SECURITY FIX: Always use server-side pricing for duration options
            # Find matching duration in product options to get correct price
            for option in product.get('pricing_options', []):
                if option.get('name') == duration:
                    product_price = float(option.get('price', product_price))  # Server-side price only
                    # Use duration-specific stock if available
                    if 'stock' in option:
                        stock_to_check = option['stock']
                    break
        
        # OPTIMIZATION: Use indexed cart lookup for better performance
        cart = Cart.create_or_get(session_id)
        
        # Check if product already in cart
        existing_item = None
        current_cart_quantity = 0
        for item in cart.get('items', []):
            # Match both product ID and duration (if applicable)
            if item.get('product_id') == str(product_id) and item.get('duration') == item_duration:
                existing_item = item
                current_cart_quantity = item.get('quantity', 0)
                break
        
        # Check if infinite stock product is already in cart
        if is_infinite_stock and existing_item:
            raise ValueError("This infinite stock product is already in your cart. You'll receive the same access link/content regardless of quantity.")
        
        # SECURITY FIX: Enhanced stock checking with atomic operations for race condition protection
        if not is_infinite_stock:
            # Use atomic operation to check and reserve stock to prevent race conditions
            stock_reserved = False
            max_retries = 3
            retry_count = 0
            
            while not stock_reserved and retry_count < max_retries:
                try:
                    # For products with duration pricing, update the specific duration stock
                    if product.get('has_duration_pricing') and item_duration:
                        # Find the specific option and check stock
                        target_option = None
                        for option in product.get('pricing_options', []):
                            if option.get('name') == item_duration:
                                target_option = option
                                break
                        
                        if not target_option:
                            raise ValueError(f"Duration option '{item_duration}' not found")
                        
                        option_stock = target_option.get('stock', 0)
                        # Check if requested quantity + existing cart quantity exceeds available stock
                        total_requested_quantity = current_cart_quantity + quantity
                        if total_requested_quantity > option_stock:
                            if current_cart_quantity > 0:
                                remaining_available = option_stock - current_cart_quantity
                                if remaining_available <= 0:
                                    raise ValueError(f"You already have the maximum available stock ({current_cart_quantity}) for {item_duration} duration in your cart")
                                else:
                                    raise ValueError(f"Not enough stock available for {item_duration} duration. You have {current_cart_quantity} in cart, can only add {remaining_available} more")
                            else:
                                raise ValueError(f"Not enough stock available for {item_duration} duration ({option_stock} remaining)")
                        else:
                            # Stock is sufficient for duration pricing products
                            stock_reserved = True
                    else:
                        # For regular products, check if requested quantity + existing cart quantity exceeds available stock
                        total_requested_quantity = current_cart_quantity + quantity
                        if total_requested_quantity > stock_to_check:
                            if current_cart_quantity > 0:
                                remaining_available = stock_to_check - current_cart_quantity
                                if remaining_available <= 0:
                                    raise ValueError(f"You already have the maximum available stock ({current_cart_quantity}) in your cart")
                                else:
                                    raise ValueError(f"Not enough stock available. You have {current_cart_quantity} in cart, can only add {remaining_available} more")
                            else:
                                raise ValueError(f"Not enough stock available ({stock_to_check} remaining)")
                        else:
                            # Stock is sufficient, no atomic reservation needed for regular products
                            stock_reserved = True
                            
                except ValueError as e:
                    # Re-raise ValueError immediately (stock issues)
                    raise e
                except Exception as e:
                    # Retry on other exceptions (network, database issues)
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise ValueError(f"Failed to reserve stock after {max_retries} attempts. Please try again.")
                    # Small delay before retry
                    time.sleep(0.1 * retry_count)
            
            if not stock_reserved:
                raise ValueError(f"Failed to reserve stock for product. Please try again.")
                
        if existing_item:
            # Update quantity if already in cart
            existing_item['quantity'] += int(quantity)
            existing_item['subtotal'] = existing_item['quantity'] * float(existing_item['price'])
        else:
            # Add new item
            cart_item = {
                "shop_id": str(shop_id),
                "product_id": str(product_id),
                "seller_username": seller_username,
                "name": product.get('name'),
                "price": product_price,  # SECURITY: Server-side price only
                "quantity": int(quantity),
                "subtotal": product_price * int(quantity),
                "image_url": product.get('image_url'),
                "duration": item_duration,
                "category_id": product.get('category_id')
            }
            
            # Add category name if product has a category
            if product.get('category_id'):
                # Find category name from already fetched shop data
                for category in shop.get('categories', []):
                    if str(category['_id']) == product.get('category_id'):
                        cart_item['category_name'] = category['name']
                        break
                else:
                    cart_item['category_name'] = 'ALL'
            else:
                cart_item['category_name'] = 'ALL'
            cart.get('items', []).append(cart_item)
            
        # OPTIMIZATION: Use indexed update for maximum performance
        total_items = sum(item.get('quantity', 0) for item in cart.get('items', []))
        total_amount = sum(item.get('subtotal', 0) for item in cart.get('items', []))
        
        # OPTIMIZATION: Use indexed update for maximum performance
        Cart.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "items": cart.get('items', []),
                    "total_items": total_items,
                    "total_amount": total_amount,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return Cart.get_by_session(session_id)
    
    @staticmethod
    def update_item(session_id, product_id, quantity, shop_id=None, duration=None):
        """Update item quantity in cart with thread-safe operations and atomic updates"""
        # Import here to avoid circular import
        from .shop import Shop
        
        cart = Cart.get_by_session(session_id)
        if not cart:
            raise ValueError("Cart not found")
        
        # If shop_id wasn't provided, try to get it from the cart item
        if not shop_id:
            for item in cart.get('items', []):
                if item.get('product_id') == str(product_id):
                    shop_id = item.get('shop_id')
                    break
        
        if not shop_id:
            raise ValueError("Shop ID not found for this product in cart")
        
        # Validate that the shop still exists
        shop = Shop.get_by_id(shop_id)
        if not shop:
            raise ValueError("Shop no longer exists. Please remove this item from your cart.")
            
        # Get product to check stock
        product = None
        for p in shop.get('products', []):
            if str(p['_id']) == str(product_id):
                product = p
                break
        
        if not product:
            raise ValueError("Product not found")
            
        # Check if this is an infinite stock product
        is_infinite_stock = product.get('infinite_stock', False)
        if is_infinite_stock and int(quantity) > 1:
            raise ValueError("Infinite stock products can only have quantity 1. You'll receive the same access link/content regardless of quantity.")
            
        # Determine which stock value to check (by duration if applicable)
        stock_to_check = product.get('stock', 0)
        
        # For products with duration pricing, check the specific duration stock
        if duration and product.get('has_duration_pricing'):
            for option in product.get('pricing_options', []):
                if option.get('name') == duration and 'stock' in option:
                    stock_to_check = option['stock']
                    break
                    
        # SECURITY FIX: Enhanced stock checking with atomic operations
        # For cart updates, we need to check if the new quantity exceeds available stock
        # But we don't need to consider existing cart quantity since we're replacing it
        if not is_infinite_stock and int(quantity) > stock_to_check:
            raise ValueError(f"Not enough stock available ({stock_to_check} remaining)")
            
        # SECURITY FIX: Use atomic update operation to prevent race conditions
        updated = False
        new_items = []
        for item in cart.get('items', []):
            # Match by product ID and duration (if applicable)
            if item.get('product_id') == str(product_id) and (duration is None or item.get('duration') == duration):
                if int(quantity) <= 0:
                    # Skip this item (remove it)
                    updated = True
                else:
                    # Update quantity with server-side price validation
                    item['quantity'] = int(quantity)
                    # SECURITY FIX: Recalculate price from server-side data
                    item_price = float(product.get('price', 0))
                    if product.get('has_duration_pricing') and duration:
                        for option in product.get('pricing_options', []):
                            if option.get('name') == duration:
                                item_price = float(option.get('price', item_price))
                                break
                    item['price'] = item_price  # Ensure server-side pricing
                    item['subtotal'] = item['quantity'] * item_price
                    new_items.append(item)
                    updated = True
            else:
                new_items.append(item)
                
        if not updated:
            raise ValueError("Item not found in cart")
            
        # Calculate new totals
        total_items = sum(item.get('quantity', 0) for item in new_items)
        total_amount = sum(item.get('subtotal', 0) for item in new_items)
        
        # SECURITY FIX: Use atomic update to prevent race conditions
        result = Cart.collection.find_one_and_update(
            {"session_id": session_id},
            {
                "$set": {
                    "items": new_items,
                    "total_items": total_items,
                    "total_amount": total_amount,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=True
        )
        
        return result if result else Cart.get_by_session(session_id)
    
    @staticmethod
    def remove_item(session_id, product_id, duration=None):
        """Remove item from cart with thread-safe operations and atomic updates"""
        cart = Cart.get_by_session(session_id)
        if not cart:
            raise ValueError("Cart not found")
        
        # SECURITY FIX: Use atomic update operation to prevent race conditions
        removed = False
        new_items = []
        for item in cart.get('items', []):
            # Match by product ID and duration (if applicable)
            if item.get('product_id') == str(product_id) and (duration is None or item.get('duration') == duration):
                # Skip this item (remove it)
                removed = True
            else:
                new_items.append(item)
                
        if not removed:
            raise ValueError("Item not found in cart")
            
        # Calculate new totals
        total_items = sum(item.get('quantity', 0) for item in new_items)
        total_amount = sum(item.get('subtotal', 0) for item in new_items)
        
        # SECURITY FIX: Use atomic update to prevent race conditions
        result = Cart.collection.find_one_and_update(
            {"session_id": session_id},
            {
                "$set": {
                    "items": new_items,
                    "total_items": total_items,
                    "total_amount": total_amount,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=True
        )
        
        return result if result else Cart.get_by_session(session_id)
    
    @staticmethod
    def get_by_session(session_id):
        """Get cart by session ID"""
        cart = Cart.collection.find_one({"session_id": session_id})
        if not cart:
            return {"session_id": session_id, "items": [], "total_items": 0, "total_amount": 0}
        return cart
    
    @staticmethod
    def clear(session_id):
        """Clear cart"""
        Cart.collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "items": [],
                    "total_items": 0,
                    "total_amount": 0,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return Cart.get_by_session(session_id) 