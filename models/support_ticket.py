"""
SupportTicket model for handling customer support tickets and merchant replies.
"""

from .base import db, ObjectId, datetime
import logging

logger = logging.getLogger(__name__)

class SupportTicket:
    collection = db.support_tickets

    @staticmethod
    def create(
        merchant_id,
        customer_id,
        shop_id,
        order_ids,
        subject,
        description,
        initial_message=None
    ):
        """Create a new support ticket"""
        try:
            # Resolve MongoDB ObjectIds to actual order IDs
            resolved_order_ids = SupportTicket.resolve_order_ids(order_ids)
            
            ticket = {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "shop_id": shop_id,
                "order_ids": resolved_order_ids,  # Store actual order IDs instead of ObjectIds
                "subject": subject,
                "description": description,
                "messages": [
                    {
                        "sender": "customer",
                        "message": initial_message or description,
                        "timestamp": datetime.utcnow(),
                        "unread_by_merchant": True,
                        "unread_by_customer": False
                    }
                ],
                "status": "open",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = SupportTicket.collection.insert_one(ticket)
            ticket["_id"] = result.inserted_id
            logger.info(f"Created new support ticket {ticket['_id']} for merchant {merchant_id}")
            return ticket
        except Exception as e:
            logger.error(f"Error creating support ticket: {e}", exc_info=True)
            raise

    @staticmethod
    def get_by_merchant(merchant_id):
        """Get all tickets for a specific merchant"""
        try:
            tickets = list(SupportTicket.collection.find({"merchant_id": merchant_id}).sort("updated_at", -1))
            logger.debug(f"Retrieved {len(tickets)} tickets for merchant {merchant_id}")
            return tickets
        except Exception as e:
            logger.error(f"Error fetching tickets for merchant {merchant_id}: {e}", exc_info=True)
            raise

    @staticmethod
    def get_by_customer(customer_id):
        """Get all tickets for a specific customer"""
        try:
            tickets = list(SupportTicket.collection.find({"customer_id": customer_id}).sort("updated_at", -1))
            logger.debug(f"Retrieved {len(tickets)} tickets for customer {customer_id}")
            return tickets
        except Exception as e:
            logger.error(f"Error fetching tickets for customer {customer_id}: {e}", exc_info=True)
            raise

    @staticmethod
    def get_by_id(ticket_id):
        """Get a specific ticket by ID"""
        try:
            ticket = SupportTicket.collection.find_one({"_id": ObjectId(ticket_id)})
            if ticket:
                logger.debug(f"Retrieved ticket {ticket_id}")
            else:
                logger.warning(f"Ticket {ticket_id} not found")
            return ticket
        except Exception as e:
            logger.error(f"Error fetching ticket {ticket_id}: {e}", exc_info=True)
            raise

    @staticmethod
    def add_reply(ticket_id, sender, message):
        """Add a reply to a ticket"""
        try:
            ticket = SupportTicket.get_by_id(ticket_id)
            if not ticket:
                raise ValueError(f"Ticket {ticket_id} not found")
            
            if sender not in ['customer', 'merchant']:
                raise ValueError(f"Invalid sender type: {sender}")
            
            reply = {
                "sender": sender,
                "message": message,
                "timestamp": datetime.utcnow(),
                "unread_by_merchant": sender == "customer",
                "unread_by_customer": sender == "merchant"
            }
            
            result = SupportTicket.collection.update_one(
                {"_id": ObjectId(ticket_id)},
                {
                    "$push": {"messages": reply},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            
            if result.modified_count == 0:
                raise ValueError(f"Failed to add reply to ticket {ticket_id}")
            
            logger.info(f"Added reply from {sender} to ticket {ticket_id}")
            return SupportTicket.get_by_id(ticket_id)
        except Exception as e:
            logger.error(f"Error adding reply to ticket {ticket_id}: {e}", exc_info=True)
            raise

    @staticmethod
    def mark_read(ticket_id, user_type):
        """Mark messages as read by a specific user type"""
        try:
            if user_type not in ['merchant', 'customer']:
                raise ValueError(f"Invalid user_type: {user_type}")
            
            field = f"messages.$[elem].unread_by_{user_type}"
            array_filter = {f"elem.unread_by_{user_type}": True}
            
            result = SupportTicket.collection.update_one(
                {"_id": ObjectId(ticket_id)},
                {"$set": {field: False}},
                array_filters=[array_filter]
            )
            
            logger.info(f"Marked messages as read by {user_type} for ticket {ticket_id}")
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error marking ticket {ticket_id} as read by {user_type}: {e}", exc_info=True)
            raise

    @staticmethod
    def update_status(ticket_id, status):
        """Update ticket status"""
        try:
            if status not in ['open', 'closed']:
                raise ValueError(f"Invalid status: {status}")
            
            result = SupportTicket.collection.update_one(
                {"_id": ObjectId(ticket_id)},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            )
            
            if result.matched_count == 0:
                logger.warning(f"Ticket {ticket_id} not found when updating status")
                return None
            
            if result.modified_count == 0:
                logger.info(f"Ticket {ticket_id} status was already {status}")
            else:
                logger.info(f"Updated ticket {ticket_id} status to {status}")
            
            return SupportTicket.get_by_id(ticket_id)
        except Exception as e:
            logger.error(f"Error updating ticket {ticket_id} status to {status}: {e}", exc_info=True)
            raise

    @staticmethod
    def close_ticket(ticket_id):
        """Close a ticket"""
        return SupportTicket.update_status(ticket_id, 'closed')

    @staticmethod
    def reopen_ticket(ticket_id):
        """Reopen a ticket"""
        return SupportTicket.update_status(ticket_id, 'open')

    @staticmethod
    def get_ticket_stats(merchant_id):
        """Get ticket statistics for a merchant"""
        try:
            pipeline = [
                {"$match": {"merchant_id": merchant_id}},
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            results = list(SupportTicket.collection.aggregate(pipeline))
            stats = {"open": 0, "closed": 0, "total": 0}
            
            for result in results:
                stats[result["_id"]] = result["count"]
                stats["total"] += result["count"]
            
            # Count unread messages
            unread_pipeline = [
                {"$match": {"merchant_id": merchant_id}},
                {"$unwind": "$messages"},
                {"$match": {"messages.unread_by_merchant": True}},
                {"$group": {"_id": "$_id"}},
                {"$count": "unread_tickets"}
            ]
            
            unread_results = list(SupportTicket.collection.aggregate(unread_pipeline))
            stats["unread"] = unread_results[0]["unread_tickets"] if unread_results else 0
            
            logger.debug(f"Retrieved stats for merchant {merchant_id}: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Error getting ticket stats for merchant {merchant_id}: {e}", exc_info=True)
            raise

    @staticmethod
    def search_tickets(merchant_id, query, status_filter=None):
        """Search tickets by subject, description, or customer"""
        try:
            match_conditions = {"merchant_id": merchant_id}
            
            if status_filter and status_filter != 'all':
                match_conditions["status"] = status_filter
            
            if query:
                match_conditions["$or"] = [
                    {"subject": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                    {"customer_id": {"$regex": query, "$options": "i"}},
                    {"order_ids": {"$elemMatch": {"$regex": query, "$options": "i"}}}
                ]
            
            tickets = list(SupportTicket.collection.find(match_conditions).sort("updated_at", -1))
            logger.debug(f"Search found {len(tickets)} tickets for query: {query}")
            return tickets
        except Exception as e:
            logger.error(f"Error searching tickets: {e}", exc_info=True)
            raise

    @staticmethod
    def get_by_id_with_stock(ticket_id):
        """Get a specific ticket by ID with sent stock information"""
        try:
            ticket = SupportTicket.get_by_id(ticket_id)
            if not ticket:
                return None
            
            # Get sent stock for all orders associated with this ticket
            from .order import Order
            sent_stock = []
            
            for order_id in ticket.get('order_ids', []):
                # Find order by custom order_id (not ObjectId)
                order = Order.collection.find_one({"order_id": order_id})
                if order and order.get('sent_stock'):
                    sent_stock.extend(order['sent_stock'])
            
            # Add sent stock to ticket
            ticket['sent_stock'] = sent_stock
            return ticket
        
        except Exception as e:
            logger.error(f"Error fetching ticket with stock {ticket_id}: {e}", exc_info=True)
            raise    

    @staticmethod
    def bulk_update_status(ticket_ids, status):
        """Update status for multiple tickets"""
        try:
            if status not in ['open', 'closed']:
                raise ValueError(f"Invalid status: {status}")
            
            object_ids = [ObjectId(tid) for tid in ticket_ids]
            
            result = SupportTicket.collection.update_many(
                {"_id": {"$in": object_ids}},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}}
            )
            
            logger.info(f"Bulk updated {result.modified_count} tickets to status {status}")
            return result.modified_count
        except Exception as e:
            logger.error(f"Error bulk updating tickets to {status}: {e}", exc_info=True)
            raise

    @staticmethod
    def bulk_mark_read(ticket_ids, user_type):
        """Mark multiple tickets as read"""
        try:
            if user_type not in ['merchant', 'customer']:
                raise ValueError(f"Invalid user_type: {user_type}")
            
            object_ids = [ObjectId(tid) for tid in ticket_ids]
            field = f"messages.$[elem].unread_by_{user_type}"
            array_filter = {f"elem.unread_by_{user_type}": True}
            
            result = SupportTicket.collection.update_many(
                {"_id": {"$in": object_ids}},
                {"$set": {field: False}},
                array_filters=[array_filter]
            )
            
            logger.info(f"Bulk marked {len(ticket_ids)} tickets as read by {user_type}")
            return result.modified_count
        except Exception as e:
            logger.error(f"Error bulk marking tickets as read: {e}", exc_info=True)
            raise

    @staticmethod
    def resolve_order_ids(order_ids):
        """Resolve MongoDB ObjectIds to actual order IDs"""
        try:
            from .order import Order
            
            resolved_orders = []
            for order_id in order_ids:
                order = Order.get_by_id(order_id)
                if order and order.get('order_id'):
                    resolved_orders.append(order['order_id'])
                else:
                    logger.warning(f"Could not resolve order ID {order_id}")
                    resolved_orders.append(str(order_id))
            
            return resolved_orders
        except Exception as e:
            logger.error(f"Error resolving order IDs: {e}", exc_info=True)
            return []