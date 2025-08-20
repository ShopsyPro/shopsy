"""
Customer models for handling customer operations.
"""

from .base import db, ObjectId, datetime, timedelta, random

class CustomerOTP:
    """Customer OTP verification system for order tracking"""
    collection = db.customer_otps
    
    @staticmethod
    def generate_otp():
        """Generate a 6-digit OTP"""
        return str(random.randint(100000, 999999))
    
    @staticmethod
    def create(email):
        """Create a new OTP for email verification"""
        email = email.lower().strip()
        otp_code = CustomerOTP.generate_otp()
        
        # Remove any existing OTP for this email
        CustomerOTP.collection.delete_many({"email": email})
        
        # Create new OTP with 2-hour expiry
        otp_record = {
            "email": email,
            "otp_code": otp_code,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=2),
            "verified": False,
            "attempts": 0,
            "max_attempts": 5
        }
        
        result = CustomerOTP.collection.insert_one(otp_record)
        otp_record["_id"] = result.inserted_id
        
        return otp_record
    
    @staticmethod
    def verify(email, otp_code):
        """Verify OTP code for email"""
        email = email.lower().strip()
        
        # Find the OTP record
        otp_record = CustomerOTP.collection.find_one({
            "email": email,
            "verified": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if not otp_record:
            return {"success": False, "message": "OTP not found or expired"}
        
        # Check max attempts
        if otp_record.get("attempts", 0) >= otp_record.get("max_attempts", 5):
            return {"success": False, "message": "Maximum verification attempts exceeded"}
        
        # Increment attempts
        CustomerOTP.collection.update_one(
            {"_id": otp_record["_id"]},
            {"$inc": {"attempts": 1}}
        )
        
        # Verify OTP code
        if otp_record["otp_code"] == otp_code:
            # Mark as verified
            CustomerOTP.collection.update_one(
                {"_id": otp_record["_id"]},
                {"$set": {"verified": True, "verified_at": datetime.utcnow()}}
            )
            return {"success": True, "message": "OTP verified successfully"}
        else:
            return {"success": False, "message": "Invalid OTP code"}
    
    @staticmethod
    def is_verified(email):
        """Check if email has a valid verified OTP"""
        email = email.lower().strip()
        
        # Check for verified OTP within last 30 minutes (session validity)
        session_cutoff = datetime.utcnow() - timedelta(minutes=30)
        
        verified_record = CustomerOTP.collection.find_one({
            "email": email,
            "verified": True,
            "verified_at": {"$gt": session_cutoff}
        })
        
        return verified_record is not None
    
    @staticmethod
    def cleanup_expired():
        """Remove expired OTP records"""
        result = CustomerOTP.collection.delete_many({
            "expires_at": {"$lt": datetime.utcnow()}
        })
        return result.deleted_count
    
    @staticmethod
    def get_by_email(email):
        """Get current OTP record for email"""
        email = email.lower().strip()
        return CustomerOTP.collection.find_one({
            "email": email,
            "verified": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })


class CustomerOrderTracker:
    """Customer order tracking across all merchants"""
    
    @staticmethod
    def get_orders_by_email(customer_email):
        """Get all orders for a customer email across all merchants"""
        # Import here to avoid circular import
        from .order import Order
        from .shop import Shop
        
        customer_email = customer_email.lower().strip()
        
        # Get all orders for this email
        orders = list(Order.collection.find({
            "customer_email": customer_email,
            "status": "completed"
        }).sort("created_at", -1))
        
        # Enrich orders with shop information
        enriched_orders = []
        for order in orders:
            # Get shop information
            shop = Shop.get_by_id(order.get("shop_id"))
            if shop:
                order["shop_name"] = shop.get("name", "Unknown Shop")
                order["shop_username"] = shop.get("owner", {}).get("username", "unknown")
                order["merchant_code"] = shop.get("merchant_code", "")
                
                # Calculate order summary
                total_items = len(order.get("items", []))
                total_stock_sent = len(order.get("sent_stock", []))
                
                order["order_summary"] = {
                    "total_items": total_items,
                    "total_stock_sent": total_stock_sent,
                    "display_id": Order.get_display_id(order),
                    "short_display_id": Order.get_short_display_id(order)
                }
                
                enriched_orders.append(order)
        
        return enriched_orders
    
    @staticmethod
    def get_order_stats(customer_email):
        """Get order statistics for customer"""
        customer_email = customer_email.lower().strip()
        
        # Get basic stats
        orders = CustomerOrderTracker.get_orders_by_email(customer_email)
        
        if not orders:
            return {
                "total_orders": 0,
                "total_spent": 0,
                "total_items": 0,
                "unique_merchants": 0,
                "first_order_date": None,
                "last_order_date": None
            }
        
        total_spent = sum(order.get("total_amount", 0) for order in orders)
        total_items = sum(len(order.get("items", [])) for order in orders)
        unique_merchants = len(set(order.get("shop_username") for order in orders if order.get("shop_username")))
        
        order_dates = [order.get("created_at") for order in orders if order.get("created_at")]
        first_order_date = min(order_dates) if order_dates else None
        last_order_date = max(order_dates) if order_dates else None
        
        return {
            "total_orders": len(orders),
            "total_spent": total_spent,
            "total_items": total_items,
            "unique_merchants": unique_merchants,
            "first_order_date": first_order_date,
            "last_order_date": last_order_date
        } 