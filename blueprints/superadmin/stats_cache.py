import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from models.shop import Shop
from models.order import Order

class StatsCache:
    """Fast caching system for super admin statistics"""
    
    def __init__(self):
        self.cache = {}
        self.last_update = {}
        self.cache_duration = 60  # Cache for 60 seconds
        self.lock = threading.Lock()
        
        # Pre-computed aggregations cache
        self.aggregations_cache = {
            'platform_stats': None,
            'merchant_stats': None,
            'revenue_stats': None,
            'order_stats': None
        }
        self.aggregations_last_update = {}
        
    def get_or_compute(self, key, compute_func, cache_duration=None):
        """Get cached value or compute and cache it"""
        cache_duration = cache_duration or self.cache_duration
        current_time = time.time()
        
        with self.lock:
            if (key in self.cache and 
                key in self.last_update and 
                current_time - self.last_update[key] < cache_duration):
                return self.cache[key]
            
            # Compute new value
            value = compute_func()
            self.cache[key] = value
            self.last_update[key] = current_time
            return value
    
    def get_platform_stats(self):
        """Get platform-wide statistics with caching"""
        def compute_stats():
            # Use single aggregation pipeline for all platform stats
            pipeline = [
                {
                    "$facet": {
                        "total_stats": [{"$count": "total_orders"}],
                        "completed_stats": [
                            {"$match": {"status": "completed"}},
                            {"$group": {
                                "_id": None,
                                "count": {"$sum": 1},
                                "revenue": {"$sum": "$total_amount"}
                            }}
                        ],
                        "pending_stats": [
                            {"$match": {"status": "pending"}},
                            {"$count": "count"}
                        ],
                        "customers": [
                            {"$match": {"customer_email": {"$exists": True, "$ne": None}}},
                            {"$group": {"_id": "$customer_email"}},
                            {"$count": "unique_customers"}
                        ],
                        "recent_orders": [
                            {"$match": {"created_at": {"$gte": datetime.utcnow() - timedelta(days=1)}}},
                            {"$count": "count"}
                        ],
                        "recent_revenue": [
                            {"$match": {
                                "status": "completed",
                                "created_at": {"$gte": datetime.utcnow() - timedelta(days=30)}
                            }},
                            {"$group": {"_id": None, "revenue": {"$sum": "$total_amount"}}}
                        ]
                    }
                }
            ]
            
            aggregation_result = list(Order.collection.aggregate(pipeline))
            if not aggregation_result:
                # If no result, return default values
                return {
                    'total_shops': 0,
                    'total_orders': 0,
                    'total_customers': 0,
                    'total_revenue': 0,
                    'completed_orders': 0,
                    'pending_orders': 0,
                    'new_orders_24h': 0,
                    'new_shops_24h': 0,
                    'new_shops_30d': 0,
                    'recent_revenue': 0,
                    'online_merchants': 0
                }
            result = aggregation_result[0]
            
            # Extract values with defaults - safely handle empty arrays
            total_stats = result.get('total_stats', [])
            total_orders = total_stats[0].get('total_orders', 0) if total_stats else 0
            
            completed_stats = result.get('completed_stats', [])
            completed_data = completed_stats[0] if completed_stats else {}
            completed_orders = completed_data.get('count', 0)
            total_revenue = completed_data.get('revenue', 0)
            
            pending_stats = result.get('pending_stats', [])
            pending_orders = pending_stats[0].get('count', 0) if pending_stats else 0
            
            customers_stats = result.get('customers', [])
            total_customers = customers_stats[0].get('unique_customers', 0) if customers_stats else 0
            
            recent_orders_stats = result.get('recent_orders', [])
            new_orders_24h = recent_orders_stats[0].get('count', 0) if recent_orders_stats else 0
            
            recent_revenue_stats = result.get('recent_revenue', [])
            recent_revenue = recent_revenue_stats[0].get('revenue', 0) if recent_revenue_stats else 0
            
            # Get shop stats separately (faster than joining)
            total_shops = Shop.collection.count_documents({})
            new_shops_24h = Shop.collection.count_documents({
                "created_at": {"$gte": datetime.utcnow() - timedelta(days=1)}
            })
            new_shops_30d = Shop.collection.count_documents({
                "created_at": {"$gte": datetime.utcnow() - timedelta(days=30)}
            })
            
            return {
                'total_shops': total_shops,
                'total_orders': total_orders,
                'total_customers': total_customers,
                'total_revenue': total_revenue,
                'completed_orders': completed_orders,
                'pending_orders': pending_orders,
                'new_orders_24h': new_orders_24h,
                'new_shops_24h': new_shops_24h,
                'new_shops_30d': new_shops_30d,
                'recent_revenue': recent_revenue,
                'online_merchants': len(Shop.get_all_online_shops())  # This should also be cached
            }
        
        return self.get_or_compute('platform_stats', compute_stats, 30)  # Cache for 30 seconds
    
    def get_top_merchants(self, limit=10):
        """Get top performing merchants with caching"""
        def compute_top_merchants():
            pipeline = [
                {"$match": {"status": "completed"}},
                {"$group": {
                    "_id": "$shop_id",
                    "total_revenue": {"$sum": "$total_amount"},
                    "order_count": {"$sum": 1}
                }},
                {"$sort": {"total_revenue": -1}},
                {"$limit": limit}
            ]
            
            top_merchants = list(Order.collection.aggregate(pipeline))
            
            # Batch get shop details
            shop_ids = [m['_id'] for m in top_merchants]
            shops = {str(s['_id']): s for s in Shop.collection.find({"_id": {"$in": shop_ids}})}
            
            for merchant in top_merchants:
                shop_id = str(merchant['_id'])
                shop = shops.get(shop_id)
                if shop:
                    merchant['shop_name'] = shop.get('name', 'Unknown Shop')
                    merchant['owner_username'] = shop.get('owner', {}).get('username', 'Unknown')
                else:
                    merchant['shop_name'] = 'Deleted Shop'
                    merchant['owner_username'] = 'Unknown'
            
            return top_merchants
        
        return self.get_or_compute(f'top_merchants_{limit}', compute_top_merchants, 120)  # Cache for 2 minutes
    
    def get_recent_orders(self, limit=10):
        """Get recent orders with shop names pre-joined"""
        def compute_recent_orders():
            # Get recent orders
            orders = list(Order.collection.find().sort("created_at", -1).limit(limit))
            
            # Batch get shop names
            shop_ids = list(set(order.get('shop_id') for order in orders if order.get('shop_id')))
            shops = {}
            if shop_ids:
                shop_cursor = Shop.collection.find({"_id": {"$in": shop_ids}}, {"name": 1})
                shops = {str(shop['_id']): shop.get('name', 'Unknown Shop') for shop in shop_cursor}
            
            # Add shop names to orders
            for order in orders:
                shop_id = str(order.get('shop_id', ''))
                order['shop_name'] = shops.get(shop_id, 'Unknown Shop')
            
            return orders
        
        return self.get_or_compute(f'recent_orders_{limit}', compute_recent_orders, 30)
    
    def get_merchant_batch_stats(self, shop_ids):
        """Get statistics for multiple merchants in one go"""
        def compute_batch_stats():
            # Convert to ObjectIds if needed
            from bson import ObjectId
            object_ids = [ObjectId(sid) if isinstance(sid, str) else sid for sid in shop_ids]
            
            # Single aggregation for all shop stats
            pipeline = [
                {"$match": {"shop_id": {"$in": object_ids}}},
                {"$group": {
                    "_id": "$shop_id",
                    "order_count": {"$sum": 1},
                    "total_revenue": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "completed"]}, "$total_amount", 0]
                        }
                    }
                }}
            ]
            
            results = list(Order.collection.aggregate(pipeline))
            return {str(r['_id']): r for r in results}
        
        cache_key = f"batch_stats_{hash(tuple(sorted(str(sid) for sid in shop_ids)))}"
        return self.get_or_compute(cache_key, compute_batch_stats, 60)
    
    def invalidate_cache(self, keys=None):
        """Invalidate specific cache keys or all cache"""
        with self.lock:
            if keys:
                for key in keys:
                    self.cache.pop(key, None)
                    self.last_update.pop(key, None)
            else:
                self.cache.clear()
                self.last_update.clear()

# Global cache instance
stats_cache = StatsCache()