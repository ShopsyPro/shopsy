"""
Scheduler module for background tasks including subscription management.
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from models import Subscription

logger = logging.getLogger(__name__)

class SubscriptionScheduler:
    """Background scheduler for subscription-related tasks"""
    
    def __init__(self):
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the scheduler"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            logger.info("Subscription scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Subscription scheduler stopped")
    
    def _run(self):
        """Main scheduler loop"""
        while self.running:
            try:
                # Run subscription cleanup every 5 minutes
                self._expire_subscriptions()
                self._update_merchant_status()
                
                # Sleep for 5 minutes
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in subscription scheduler: {e}")
                # Sleep for 1 minute on error before retrying
                time.sleep(60)
    
    def _expire_subscriptions(self):
        """Expire unpaid subscriptions that have passed their expiry time"""
        try:
            expired_count = Subscription.expire_unpaid_subscriptions()
            if expired_count > 0:
                logger.info(f"Expired {expired_count} unpaid subscriptions")
        except Exception as e:
            logger.error(f"Error expiring subscriptions: {e}")
    
    def _update_merchant_status(self):
        """Update merchant status for expired paid subscriptions"""
        try:
            updated_count = Subscription.expire_ended_subscriptions()
            if updated_count > 0:
                logger.info(f"Updated {updated_count} merchants to unpaid status")
        except Exception as e:
            logger.error(f"Error updating merchant status: {e}")

# Global scheduler instance
scheduler = SubscriptionScheduler()

def init_scheduler(app):
    """Initialize scheduler with Flask app"""
    if app.config.get('TESTING'):
        # Don't start scheduler during testing
        return
    
    # Start scheduler when app starts
    scheduler.start()
    
    # Stop scheduler when app shuts down
    import atexit
    atexit.register(scheduler.stop)
    
    logger.info("Subscription scheduler initialized")

def run_manual_cleanup():
    """Manual subscription cleanup - useful for testing or one-off runs"""
    try:
        logger.info("Running manual subscription cleanup...")
        
        # Expire unpaid subscriptions
        expired_count = Subscription.expire_unpaid_subscriptions()
        logger.info(f"Expired {expired_count} unpaid subscriptions")
        
        # Update merchant status for expired subscriptions
        updated_count = Subscription.expire_ended_subscriptions()
        logger.info(f"Updated {updated_count} merchants to unpaid status")
        
        return {
            'success': True,
            'expired_subscriptions': expired_count,
            'updated_merchants': updated_count
        }
        
    except Exception as e:
        logger.error(f"Error during manual cleanup: {e}")
        return {
            'success': False,
            'error': str(e)
        }
