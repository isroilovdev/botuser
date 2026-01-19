import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

DEFAULT_INTERVAL = 305  # 5 min 5 sek
SESSION_DIR = 'sessions'

os.makedirs(SESSION_DIR, exist_ok=True)