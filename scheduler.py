import asyncio
import logging
from telethon.errors import FloodWaitError, UserBannedInChannelError

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, bot, db, mtproto_mgr):
        self.bot = bot
        self.db = db
        self.mtproto_mgr = mtproto_mgr
        self.tasks = {}
    
    async def send_message_once(self, user_id):
        """Send message once to target group"""
        try:
            user = self.db.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return False
            
            message_text = self.db.get_message(user_id)
            if not message_text:
                logger.error(f"No message for user {user_id}")
                return False
            
            target_group = self.db.get_target_group()
            if not target_group:
                logger.error("No target group set")
                return False
            
            client = await self.mtproto_mgr.get_client(user_id, user['session_string'])
            
            await client.send_message(target_group, message_text)
            logger.info(f"Message sent by user {user_id}")
            return True
            
        except FloodWaitError as e:
            logger.warning(f"FloodWait {e.seconds}s for user {user_id}")
            await asyncio.sleep(e.seconds)
            return False
        
        except UserBannedInChannelError:
            logger.error(f"User {user_id} banned in channel")
            self.stop_sender(user_id)
            return False
        
        except Exception as e:
            logger.error(f"Send error for user {user_id}: {e}")
            return False
    
    async def sender_loop(self, user_id):
        """Main sending loop for a user"""
        logger.info(f"Starting sender loop for user {user_id}")
        
        # Send immediately on start
        await self.send_message_once(user_id)
        
        while self.db.is_sending_active(user_id):
            try:
                interval = self.db.get_interval()
                await asyncio.sleep(interval)
                
                if not self.db.is_sending_active(user_id):
                    break
                
                await self.send_message_once(user_id)
            except asyncio.CancelledError:
                logger.info(f"Sender loop cancelled for user {user_id}")
                break
            except Exception as e:
                logger.error(f"Sender loop error for user {user_id}: {e}")
                await asyncio.sleep(60)  # Wait 1 min before retry
        
        logger.info(f"Sender loop stopped for user {user_id}")
    
    def start_sender(self, user_id):
        """Start sending loop for user"""
        if user_id in self.tasks and not self.tasks[user_id].done():
            logger.info(f"Sender already running for user {user_id}")
            return
        
        self.db.set_sending_active(user_id, True)
        task = asyncio.create_task(self.sender_loop(user_id))
        self.tasks[user_id] = task
        logger.info(f"Started sender for user {user_id}")
    
    def stop_sender(self, user_id):
        """Stop sending loop for user"""
        self.db.set_sending_active(user_id, False)
        
        if user_id in self.tasks:
            task = self.tasks[user_id]
            if not task.done():
                task.cancel()
            del self.tasks[user_id]
        
        logger.info(f"Stopped sender for user {user_id}")
    
    def is_active(self, user_id):
        """Check if sender is active"""
        return self.db.is_sending_active(user_id)
    
    def get_active_count(self):
        """Get count of active senders"""
        return len([u for u in self.db.get_all_users() if self.db.is_sending_active(u['user_id'])])
    
    async def restore_senders(self):
        """Restore active senders after restart"""
        active_users = self.db.get_active_users()
        logger.info(f"Restoring {len(active_users)} active senders")
        
        for user in active_users:
            self.start_sender(user['user_id'])