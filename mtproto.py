import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_DIR

class MTProtoManager:
    def __init__(self):
        self.clients = {}
    
    async def create_client(self, user_id):
        """Create new MTProto client for login"""
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        return client
    
    def save_session(self, user_id, client):
        """Save session string after successful login"""
        session_str = client.session.save()
        return session_str
    
    async def load_client(self, user_id, session_string):
        """Load existing client from session string"""
        if user_id in self.clients:
            return self.clients[user_id]
        
        session = StringSession(session_string)
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            raise Exception("Session expired")
        
        self.clients[user_id] = client
        return client
    
    def delete_session(self, user_id):
        """Delete session and disconnect client"""
        if user_id in self.clients:
            client = self.clients[user_id]
            try:
                client.disconnect()
            except:
                pass
            del self.clients[user_id]
    
    async def get_client(self, user_id, session_string):
        """Get or create client"""
        if user_id in self.clients:
            return self.clients[user_id]
        return await self.load_client(user_id, session_string)
    
    def disconnect_all(self):
        """Disconnect all clients"""
        for user_id in list(self.clients.keys()):
            try:
                client = self.clients[user_id]
                if client.is_connected():
                    client.disconnect()
            except Exception:
                pass
        self.clients.clear()