import sqlite3
from contextlib import contextmanager
from config import DEFAULT_INTERVAL

class Database:
    def __init__(self, db_path='data.db'):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    phone TEXT NOT NULL,
                    session_string TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    user_id INTEGER PRIMARY KEY,
                    message_text TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sending_state (
                    user_id INTEGER PRIMARY KEY,
                    is_active INTEGER DEFAULT 0,
                    last_sent TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            
            conn.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_active ON sending_state(is_active)')
            
            conn.execute('''
                INSERT OR IGNORE INTO settings (key, value) VALUES ('interval', ?)
            ''', (str(DEFAULT_INTERVAL),))
    
    def add_user(self, user_id, phone, session_string):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO users (user_id, phone, session_string)
                VALUES (?, ?, ?)
            ''', (user_id, phone, session_string))
    
    def get_user(self, user_id):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            if row:
                return {
                    'user_id': row['user_id'],
                    'phone': row['phone'] if 'phone' in row.keys() else '',
                    'session_string': row['session_string'] if 'session_string' in row.keys() else '',
                    'created_at': row['created_at'] if 'created_at' in row.keys() else ''
                }
            return None
    
    def delete_user(self, user_id):
        with self.get_conn() as conn:
            conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM sending_state WHERE user_id = ?', (user_id,))
    
    def get_all_users(self):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT * FROM users')
            rows = cur.fetchall()
            return [{'user_id': r['user_id'], 'phone': r['phone'], 'session_string': r['session_string']} for r in rows]
    
    def save_message(self, user_id, message_text):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO messages (user_id, message_text, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, message_text))
    
    def get_message(self, user_id):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT message_text FROM messages WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return row['message_text'] if row else None
    
    def set_sending_active(self, user_id, is_active):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO sending_state (user_id, is_active, last_sent)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, 1 if is_active else 0))
    
    def is_sending_active(self, user_id):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT is_active FROM sending_state WHERE user_id = ?', (user_id,))
            row = cur.fetchone()
            return bool(row['is_active']) if row else False
    
    def get_active_users(self):
        with self.get_conn() as conn:
            cur = conn.execute('''
                SELECT u.* FROM users u
                JOIN sending_state s ON u.user_id = s.user_id
                WHERE s.is_active = 1
            ''')
            return [dict(row) for row in cur.fetchall()]
    
    def set_target_group(self, group_id):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO settings (key, value) VALUES ('target_group', ?)
            ''', (str(group_id),))
    
    def get_target_group(self):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT value FROM settings WHERE key = ?', ('target_group',))
            row = cur.fetchone()
            return int(row['value']) if row else None
    
    def set_interval(self, seconds):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO settings (key, value) VALUES ('interval', ?)
            ''', (str(seconds),))
    
    def get_interval(self):
        with self.get_conn() as conn:
            cur = conn.execute('SELECT value FROM settings WHERE key = ?', ('interval',))
            row = cur.fetchone()
            return int(row['value']) if row else DEFAULT_INTERVAL