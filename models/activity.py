"""
Activity model for handling activity logging.
"""

from .base import db, ObjectId, datetime, timedelta

class ActivityLog:
    collection = db.activity_logs
    
    @staticmethod
    def log_activity(user_id, action_type, item_type, item_id=None, details=None):
        """Log an activity in the shop
        
        Args:
            user_id: User ID
            action_type: One of 'create', 'update', 'delete'
            item_type: One of 'product', 'category', 'coupon', 'order'
            item_id: ID of the affected item
            details: Additional details about the action
        """
        activity = {
            "user_id": ObjectId(user_id),
            "action_type": action_type,
            "item_type": item_type,
            "item_id": ObjectId(item_id) if item_id else None,
            "details": details,
            "timestamp": datetime.utcnow()
        }
        result = ActivityLog.collection.insert_one(activity)
        activity["_id"] = result.inserted_id
        return activity
    
    @staticmethod
    def get_recent_by_user(user_id, hours=12):
        """Get recent activity logs for a user within the specified hours"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        return list(ActivityLog.collection.find({
            "user_id": ObjectId(user_id),
            "timestamp": {"$gte": start_time}
        }).sort("timestamp", -1)) 