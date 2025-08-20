"""
Order model for handling order operations.
"""

from .base import db, ObjectId, datetime, random, string

class Order:
    collection = db.orders
    failed_collection = db.failed_orders
    
    @staticmethod
    def create(shop_id, session_id, items, total_amount, customer_email=None, status='completed', coupon=None):
        """Create a new order"""
        # Calculate original total (before discount)
        original_total = sum(item.get('subtotal', 0) for item in items)
        discount_total = original_total - float(total_amount) if original_total > float(total_amount) else 0
        
        # Generate custom order ID
        custom_order_id = Order.generate_order_id(shop_id)
        
        # First, create the order in the orders collection for efficient querying
        order = {
            "shop_id": ObjectId(shop_id),
            "order_id": custom_order_id,  # Custom human-readable ID
            "session_id": session_id,
            "items": items,
            "original_total": original_total,  # Total before discount
            "discount_total": discount_total,  # Amount of discount
            "total_amount": float(total_amount),  # Final amount after discount
            "customer_email": customer_email,
            "status": status,
            "sent_stock": [],  # Track stock items sent to customer
            "created_at": datetime.utcnow()
        }
        
        # Add coupon information if provided
        if coupon:
            order["coupon"] = {
                "code": coupon.get("code"),
                "discount_percentage": coupon.get("discount_percentage", 0),
                "category_id": coupon.get("category_id"),
                "coupon_id": str(coupon.get("_id")),
                "category_name": coupon.get("category_name")
            }
        
        result = Order.collection.insert_one(order)
        order["_id"] = result.inserted_id
        
        # If order is created as completed, send stock items immediately
        if status == 'completed':
            Order.send_stock_items(str(order["_id"]))
        
        # Log the activity with more detailed information
        # Import here to avoid circular import
        from .shop import Shop
        
        items_summary = ", ".join([f"{item.get('quantity')}x {item.get('name')}" for item in items[:2]])
        if len(items) > 2:
            items_summary += f", and {len(items) - 2} more items"
            
        if coupon:
            Shop.log_activity(
                shop_id, 
                "create", 
                "order", 
                str(order["_id"]), 
                f"Order received: ${total_amount} (${discount_total} saved with coupon {coupon.get('code')}). Items: {items_summary}"
            )
        else:
            Shop.log_activity(
                shop_id, 
                "create", 
                "order", 
                str(order["_id"]), 
                f"Order received: ${total_amount}. Items: {items_summary}"
            )
        
        return order
    
    @staticmethod
    def get_by_shop(shop_id):
        """Get all orders for a specific shop"""
        return list(Order.collection.find({"shop_id": ObjectId(shop_id)}).sort("created_at", -1))
    
    @staticmethod
    def get_by_id(order_id):
        """Get an order by ID (checks both orders and failed_orders collections)"""
        # First check in orders collection
        order = Order.collection.find_one({"_id": ObjectId(order_id)})
        if order:
            return order
        
        # If not found, check in failed_orders collection
        return Order.failed_collection.find_one({"_id": ObjectId(order_id)})
    
    @staticmethod
    def get_failed_orders(shop_id=None):
        """Get all failed orders, optionally filtered by shop_id"""
        if shop_id:
            return list(Order.failed_collection.find({"shop_id": ObjectId(shop_id)}).sort("failed_at", -1))
        else:
            return list(Order.failed_collection.find().sort("failed_at", -1))
    
    @staticmethod
    def restore_failed_order(order_id):
        """Restore a failed/expired order back to the main orders collection"""
        # Get the failed/expired order
        failed_order = Order.failed_collection.find_one({"_id": ObjectId(order_id)})
        if not failed_order:
            raise ValueError(f"Failed/expired order not found: {order_id}")
        
        # Remove timestamp fields and set status back to pending
        failed_order['status'] = 'pending'
        if 'failed_at' in failed_order:
            del failed_order['failed_at']
        if 'expired_at' in failed_order:
            del failed_order['expired_at']
        
        # Insert back into orders collection
        Order.collection.insert_one(failed_order)
        
        # Remove from failed_orders collection
        Order.failed_collection.delete_one({"_id": ObjectId(order_id)})
        
        # Log the activity
        from .shop import Shop
        Shop.log_activity(
            failed_order.get("shop_id"), 
            "restore", 
            "order", 
            str(order_id), 
            f"Failed/expired order restored to pending status"
        )
        
        return failed_order
    
    @staticmethod
    def update_status(order_id, status):
        """Update an order's status with validation"""
        # Valid order statuses
        valid_statuses = {'pending', 'completed', 'expired', 'failed'}
        
        if status not in valid_statuses:
            raise ValueError(f"Invalid order status: {status}. Valid statuses are: {', '.join(valid_statuses)}")
        
        # Get current order to validate transitions
        order = Order.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")
        
        current_status = order.get('status')
        
        # Define valid status transitions
        valid_transitions = {
            'pending': {'completed', 'expired', 'failed'},
            'completed': {'expired'},  # Can only expire a completed order
            'expired': {'completed'},   # Can manually complete an expired order
            'failed': {'completed'}     # Can manually complete a failed order
        }
        
        # Validate status transition
        if current_status in valid_transitions and status not in valid_transitions[current_status]:
            raise ValueError(f"Invalid status transition from '{current_status}' to '{status}'. Valid transitions from '{current_status}' are: {', '.join(valid_transitions[current_status])}")
        
        # If status is being changed to failed or expired, move to failed_orders collection
        if status in ['failed', 'expired']:
            # Add timestamp based on status
            if status == 'failed':
                order['failed_at'] = datetime.utcnow()
            else:
                order['expired_at'] = datetime.utcnow()
            
            order['status'] = status
            
            # Move to failed_orders collection
            Order.failed_collection.insert_one(order)
            
            # Remove from orders collection
            Order.collection.delete_one({"_id": ObjectId(order_id)})
            
            # Log the activity
            from .shop import Shop
            Shop.log_activity(
                order.get("shop_id"), 
                "update", 
                "order", 
                str(order_id), 
                f"Order status updated from '{current_status}' to '{status}' - moved to failed orders"
            )
            
            return order
        else:
            # Update the order status in the main collection (only pending/completed stay here)
            Order.collection.update_one(
                {"_id": ObjectId(order_id)},
                {"$set": {"status": status}}
            )
            
            # Log the activity
            from .shop import Shop
            Shop.log_activity(
                order.get("shop_id"), 
                "update", 
                "order", 
                str(order_id), 
                f"Order status updated from '{current_status}' to '{status}'"
            )
            
            # If order is marked as completed, send stock items via email
            if status == 'completed':
                Order.send_stock_items(order_id)
            
            return Order.get_by_id(order_id)
    
    @staticmethod
    def send_stock_items(order_id):
        """Send stock items to customer via email"""
        import time
        start_time = time.time()
        
        try:
            # Import here to avoid circular import
            from .shop import Shop
            from core.email import EmailService
            
            # Get order details
            order = Order.get_by_id(order_id)
            if not order:
                print(f"Order {order_id} not found")
                return False
                
            shop_id = order.get("shop_id")
            customer_email = order.get("customer_email")
            shop_name = order.get("shop_name", "Shop")
            
            if not customer_email:
                print(f"No customer email for order {order_id}")
                return False
            
            # Initialize email service
            email_service = EmailService()
            
            # OPTIMIZATION: Get shop and all products in single query
            shop = Shop.get_by_id(shop_id)
            if not shop:
                print(f"Shop {shop_id} not found for order {order_id}")
                return False
            
            # Create products lookup dictionary for O(1) access
            products_dict = {}
            for product in shop.get('products', []):
                products_dict[str(product['_id'])] = product
            
            sent_stock = []
            all_stock_items = []
            
            # Process each item in the order
            for item in order.get("items", []):
                product_id = item.get("product_id")
                quantity = item.get("quantity", 1)
                duration = item.get("duration")
                product_name = item.get("name", "Unknown Product")
                
                # OPTIMIZATION: Get product from pre-fetched shop data (no database query)
                product = products_dict.get(product_id)
                if not product:
                    print(f"Product {product_id} not found in shop {shop_id}")
                    continue
                
                # Check if this is an infinite stock product
                is_infinite_stock = product.get("infinite_stock", False)
                
                # Determine which stock values to use
                available_stock = []
                if duration and product.get("has_duration_pricing"):
                    # Use duration-specific stock values
                    for option in product.get("pricing_options", []):
                        if option.get("name") == duration:
                            available_stock = option.get("stock_values", []).copy()  # Create a copy
                            break
                else:
                    # Use main product stock values
                    available_stock = product.get("stock_values", []).copy()  # Create a copy
                
                # For infinite products, we only need to check if there's at least one stock value
                if is_infinite_stock:
                    if not available_stock:
                        print(f"Warning: Infinite product {product_name} has no stock value defined")
                        continue
                        
                    # For infinite stock, use the same stock item for all quantities
                    stock_item = available_stock[0]  # Use the first (and typically only) stock value
                    
                    # Deliver the same stock item for each quantity requested
                    for i in range(quantity):
                        stock_data = {
                            "product_id": product_id,
                            "product_name": product_name,
                            "stock_item": stock_item,
                            "sent_at": datetime.utcnow(),
                            "duration": duration
                        }
                        sent_stock.append(stock_data)
                        all_stock_items.append(stock_data)
                        
                        # DO NOT remove stock item for infinite products
                        # The same value can be delivered to unlimited customers
                else:
                    # Handle limited stock products (existing logic)
                    # Check if we have enough stock
                    if len(available_stock) < quantity:
                        print(f"Warning: Not enough stock for product {product_name}. Available: {len(available_stock)}, Requested: {quantity}")
                        # Continue with available stock
                    
                    # Collect stock items for this product
                    for i in range(min(quantity, len(available_stock))):
                        if available_stock:
                            # Pick a random stock item from available stock
                            stock_item = random.choice(available_stock)
                            
                            # Remove the selected item from available stock to ensure uniqueness
                            available_stock.remove(stock_item)
                            
                            # Add to sent stock list
                            stock_data = {
                                "product_id": product_id,
                                "product_name": product_name,
                                "stock_item": stock_item,
                                "sent_at": datetime.utcnow(),
                                "duration": duration
                            }
                            sent_stock.append(stock_data)
                            all_stock_items.append(stock_data)
                            
                            # Remove the sent stock item from product database (only for limited stock)
                            Order._remove_stock_item(shop_id, product_id, stock_item, duration)
            
            # Send one email with all stock items
            if all_stock_items:
                # Get the proper display ID for the order
                display_id = Order.get_display_id(order)
                
                print(f"[ORDER] Sending delivery email for order {order_id} to {customer_email}")
                print(f"[ORDER] Stock items to deliver: {len(all_stock_items)}")
                
                if email_service:
                    email_sent = email_service.send_order_delivery_email(
                        to_email=customer_email,
                        order_id=display_id,
                        shop_name=shop_name,
                        stock_items=all_stock_items  # Pass all items instead of single item
                    )
                    print(f"[ORDER] Delivery email sent: {email_sent}")
                else:
                    print(f"[ORDER] Email service not available, skipping email send")
                    email_sent = False
                    
                # If email was sent successfully, update order with sent stock information and send invoice
                if email_sent:
                    # Update order with sent stock information
                    Order.collection.update_one(
                        {"_id": ObjectId(order_id)},
                        {"$set": {"sent_stock": sent_stock}}
                    )
                    
                    # Log activity (without exposing customer email)
                    Shop.log_activity(
                        shop_id,
                        "update",
                        "order",
                        str(order_id),
                        f"Stock items delivered: {len(sent_stock)} items"
                    )
                    
                    try:
                        # Send invoice email
                        invoice_sent = email_service.send_invoice_email(
                            to_email=customer_email,
                            order_id=display_id,
                            shop_name=shop_name,
                            order_data=order
                        )
                        print(f"[ORDER] Invoice email sent: {invoice_sent}")
                                
                    except Exception as e:
                        print(f"Error sending invoice email: {str(e)}")
                        
                else:
                    # If email failed, return stock items to inventory (only for limited stock products)
                    # Note: Since we send all items in a single email, if email fails, none were delivered
                    # So we can safely return all limited stock items to inventory
                    for stock_data in all_stock_items:
                        # OPTIMIZATION: Check if this was from an infinite stock product using pre-fetched data
                        product = products_dict.get(stock_data["product_id"])
                        if product and not product.get("infinite_stock", False):
                            # Only return stock to inventory for limited stock products
                            # Infinite stock items don't need to be returned since they weren't removed
                            Order._add_stock_item(shop_id, stock_data["product_id"], stock_data["stock_item"], stock_data.get("duration"))
                    
                    # Log the failure for debugging
                    print(f"[ORDER] Email delivery failed for order {order_id}. Stock items returned to inventory.")
            
            # Performance logging
            duration = time.time() - start_time
            if duration > 1.0:
                print(f"[PERFORMANCE] Slow order processing: {duration:.2f}s for order {order_id}")
            elif duration > 0.5:
                print(f"[PERFORMANCE] Moderate order processing: {duration:.2f}s for order {order_id}")
            
            return True
            
        except Exception as e:
            print(f"Error sending stock items: {str(e)}")
            return False
    
    @staticmethod
    def _remove_stock_item(shop_id, product_id, stock_item, duration=None):
        """Remove a specific stock item from product inventory"""
        try:
            # OPTIMIZATION: Get shop and product in single query instead of separate queries
            from .shop import Shop
            
            shop = Shop.get_by_id(shop_id)
            if not shop:
                return False
            
            # Find product in shop data (no separate query)
            product = None
            for p in shop.get('products', []):
                if str(p['_id']) == str(product_id):
                    product = p
                    break
            
            if not product:
                return False
            
            if duration and product.get("has_duration_pricing"):
                # Remove from duration-specific stock
                for i, option in enumerate(product.get("pricing_options", [])):
                    if option.get("name") == duration:
                        stock_values = option.get("stock_values", [])
                        if stock_item in stock_values:
                            stock_values.remove(stock_item)
                            # Update the specific option's stock values and count
                            update_result = Shop.collection.update_one(
                                {
                                    "_id": ObjectId(shop_id),
                                    "products._id": ObjectId(product_id),
                                    "products.pricing_options.name": duration
                                },
                                {
                                    "$set": {
                                        f"products.$.pricing_options.$[elem].stock_values": stock_values,
                                        f"products.$.pricing_options.$[elem].stock": len(stock_values)
                                    }
                                },
                                array_filters=[{"elem.name": duration}]
                            )
                            return update_result.modified_count > 0
            else:
                # Remove from main product stock
                stock_values = product.get("stock_values", [])
                if stock_item in stock_values:
                    stock_values.remove(stock_item)
                    new_stock_count = len(stock_values)
                    
                    # Update product stock values and count
                    update_result = Shop.collection.update_one(
                        {
                            "_id": ObjectId(shop_id),
                            "products._id": ObjectId(product_id)
                        },
                        {
                            "$set": {
                                "products.$.stock_values": stock_values,
                                "products.$.stock": new_stock_count
                            }
                        }
                    )
                    return update_result.modified_count > 0
            
            return False
            
        except Exception as e:
            print(f"Error removing stock item: {str(e)}")
            return False

    @staticmethod
    def _add_stock_item(shop_id, product_id, stock_item, duration=None):
        """Add a specific stock item back to product inventory"""
        try:
            # OPTIMIZATION: Get shop and product in single query instead of separate queries
            from .shop import Shop
            
            shop = Shop.get_by_id(shop_id)
            if not shop:
                return False
            
            # Find product in shop data (no separate query)
            product = None
            for p in shop.get('products', []):
                if str(p['_id']) == str(product_id):
                    product = p
                    break
            
            if not product:
                return False
            
            if duration and product.get("has_duration_pricing"):
                # Add to duration-specific stock
                for i, option in enumerate(product.get("pricing_options", [])):
                    if option.get("name") == duration:
                        stock_values = option.get("stock_values", [])
                        if stock_item not in stock_values:  # Avoid duplicates
                            stock_values.append(stock_item)
                            # Update the specific option's stock values and count
                            update_result = Shop.collection.update_one(
                                {
                                    "_id": ObjectId(shop_id),
                                    "products._id": ObjectId(product_id),
                                    "products.pricing_options.name": duration
                                },
                                {
                                    "$set": {
                                        f"products.$.pricing_options.$[elem].stock_values": stock_values,
                                        f"products.$.pricing_options.$[elem].stock": len(stock_values)
                                    }
                                },
                                array_filters=[{"elem.name": duration}]
                            )
                            return update_result.modified_count > 0
            else:
                # Add to main product stock
                stock_values = product.get("stock_values", [])
                if stock_item not in stock_values:  # Avoid duplicates
                    stock_values.append(stock_item)
                    new_stock_count = len(stock_values)
                    
                    # Update product stock values and count
                    update_result = Shop.collection.update_one(
                        {
                            "_id": ObjectId(shop_id),
                            "products._id": ObjectId(product_id)
                        },
                        {
                            "$set": {
                                "products.$.stock_values": stock_values,
                                "products.$.stock": new_stock_count
                            }
                        }
                    )
                    return update_result.modified_count > 0
            
            return False
            
        except Exception as e:
            print(f"Error adding stock item: {str(e)}")
            return False

    @staticmethod
    def generate_order_id(shop_id):
        """Generate a custom order ID in format: MERCHANT_CODE-TIMESTAMP_HASH-SEQ-XX"""
        # Import here to avoid circular import
        from .shop import Shop
        
        # Get shop info
        shop = Shop.get_by_id(shop_id)
        if not shop:
            return str(ObjectId())  # Fallback to ObjectId
        
        # Get or generate merchant code
        merchant_code = shop.get('merchant_code')
        if not merchant_code:
            # Generate merchant code from username
            username = shop.get('owner', {}).get('username', 'user')
            merchant_code = Shop.generate_merchant_code(username)
            
            # Save merchant code to shop record
            Shop.collection.update_one(
                {"_id": ObjectId(shop_id)},
                {"$set": {"merchant_code": merchant_code}}
            )
        
        # Get timestamp hash
        timestamp_hash = Shop.get_timestamp_hash()
        
        # Get sequence number (daily counter)
        sequence = Shop.get_next_sequence_number(shop_id)
        
        # Generate 2 random alphanumeric characters
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
        
        # Format: MERCHANT_CODE-TIMESTAMP_HASH-SEQ-XX
        order_id = f"{merchant_code}-{timestamp_hash}-{sequence:03d}-{random_chars}"
        return order_id
    
    @staticmethod
    def get_display_id(order):
        """Get the display ID for an order/invoice (same ID for both)"""
        custom_id = order.get('order_id')
        if custom_id:
            return custom_id
        else:
            # Fallback to truncated ObjectId for existing orders
            return str(order.get('_id', ''))[:8]
    
    @staticmethod
    def get_short_display_id(order):
        """Get a short display ID for an order (just the last part for space-constrained UI)"""
        custom_id = order.get('order_id')
        if custom_id and '-' in custom_id:
            # For format: MERCHANT_CODE-TIMESTAMP_HASH-SEQ-XX
            # Return: SEQ-XX (last two parts)
            parts = custom_id.split('-')
            if len(parts) >= 2:
                return f"{parts[-2]}-{parts[-1]}"
        elif custom_id:
            return custom_id
        else:
            # Fallback to truncated ObjectId for existing orders
            return str(order.get('_id', ''))[:8] 