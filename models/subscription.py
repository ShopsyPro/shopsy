"""
Subscription model for handling merchant subscription operations.
"""

from .base import (
    db, ObjectId, datetime, timedelta, uuid
)

class Subscription:
    collection = db.subscriptions
    
    @staticmethod
    def create(merchant_id, currency, amount, payment_link=None, crypto_invoice_id=None, webhook_payload=None):
        """Create a new subscription for a merchant"""
        
        subscription = {
            "merchant_id": ObjectId(merchant_id),
            "currency": currency.upper(),  # BTC/USDT/BNB
            "amount": float(amount),
            "status": "pending",  # pending/paid/expired
            "payment_link": payment_link,
            "crypto_invoice_id": crypto_invoice_id,
            "webhook_payload": webhook_payload,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=90),  # 90 minutes expiry
            "starts_at": None,  # Set when payment is confirmed
            "ends_at": None,    # Set when payment is confirmed (starts_at + 30 days)
        }
        
        result = Subscription.collection.insert_one(subscription)
        subscription["_id"] = result.inserted_id
        return subscription
    
    @staticmethod
    def get_by_id(subscription_id):
        """Get a subscription by ID"""
        return Subscription.collection.find_one({"_id": ObjectId(subscription_id)})
    
    @staticmethod
    def get_by_merchant_id(merchant_id, status=None):
        """Get subscriptions by merchant ID"""
        query = {"merchant_id": ObjectId(merchant_id)}
        if status:
            query["status"] = status
        return list(Subscription.collection.find(query).sort("created_at", -1))
    
    @staticmethod
    def get_by_crypto_invoice_id(crypto_invoice_id):
        """Get subscription by Cryptomus invoice ID"""
        return Subscription.collection.find_one({"crypto_invoice_id": crypto_invoice_id})
    
    @staticmethod
    def get_active_subscription(merchant_id):
        """Get the active (paid and not expired) subscription for a merchant"""
        now = datetime.utcnow()
        return Subscription.collection.find_one({
            "merchant_id": ObjectId(merchant_id),
            "status": "paid",
            "ends_at": {"$gt": now}
        })
    
    @staticmethod
    def get_pending_subscription(merchant_id):
        """Get the most recent pending subscription for a merchant"""
        now = datetime.utcnow()
        return Subscription.collection.find_one({
            "merchant_id": ObjectId(merchant_id),
            "status": "pending",
            "expires_at": {"$gt": now}
        }, sort=[("created_at", -1)])
    
    @staticmethod
    def update_subscription(subscription_id, **kwargs):
        """Update a subscription"""
        kwargs["updated_at"] = datetime.utcnow()
        
        result = Subscription.collection.update_one(
            {"_id": ObjectId(subscription_id)},
            {"$set": kwargs}
        )
        
        return result.modified_count > 0
    
    @staticmethod
    def mark_as_paid(subscription_id, webhook_payload=None):
        """Mark subscription as paid and set start/end dates"""
        now = datetime.utcnow()
        ends_at = now + timedelta(days=30)  # 30 days duration
        
        update_data = {
            "status": "paid",
            "starts_at": now,
            "ends_at": ends_at,
            "updated_at": now
        }
        
        if webhook_payload:
            update_data["webhook_payload"] = webhook_payload
        
        result = Subscription.collection.update_one(
            {"_id": ObjectId(subscription_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            # Update merchant's is_paid status
            from .shop import Shop
            subscription = Subscription.get_by_id(subscription_id)
            if subscription:
                Shop.collection.update_one(
                    {"_id": subscription["merchant_id"]},
                    {"$set": {"is_paid": True, "updated_at": now}}
                )
        
        return result.modified_count > 0
    
    @staticmethod
    def expire_unpaid_subscriptions():
        """Expire all unpaid subscriptions that have passed their expiry time"""
        now = datetime.utcnow()
        
        result = Subscription.collection.update_many(
            {
                "status": "pending",
                "expires_at": {"$lt": now}
            },
            {
                "$set": {
                    "status": "expired",
                    "updated_at": now
                }
            }
        )
        
        return result.modified_count
    
    @staticmethod
    def expire_ended_subscriptions():
        """Check and update merchant status for expired subscriptions"""
        now = datetime.utcnow()
        
        # Find all paid subscriptions that have ended
        expired_subscriptions = list(Subscription.collection.find({
            "status": "paid",
            "ends_at": {"$lt": now}
        }))
        
        # Update merchant status for each expired subscription
        from .shop import Shop
        updated_merchants = []
        
        for subscription in expired_subscriptions:
            merchant_id = subscription["merchant_id"]
            
            # Check if merchant has any other active subscription
            active_subscription = Subscription.get_active_subscription(merchant_id)
            
            if not active_subscription and merchant_id not in updated_merchants:
                # No active subscription found, set merchant to unpaid
                Shop.collection.update_one(
                    {"_id": merchant_id},
                    {"$set": {"is_paid": False, "updated_at": now}}
                )
                updated_merchants.append(merchant_id)
        
        return len(updated_merchants)
    
    @staticmethod
    def get_subscription_history(merchant_id, limit=None):
        """Get subscription history for a merchant"""
        query = {"merchant_id": ObjectId(merchant_id)}
        cursor = Subscription.collection.find(query).sort("created_at", -1)
        
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    @staticmethod
    def get_subscription_stats():
        """Get subscription statistics for admin dashboard"""
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_amount": {"$sum": "$amount"}
                }
            }
        ]
        
        result = list(Subscription.collection.aggregate(pipeline))
        
        stats = {
            "pending": {"count": 0, "total_amount": 0},
            "paid": {"count": 0, "total_amount": 0},
            "expired": {"count": 0, "total_amount": 0}
        }
        
        for item in result:
            if item["_id"] in stats:
                stats[item["_id"]] = {
                    "count": item["count"],
                    "total_amount": item["total_amount"]
                }
        
        return stats
