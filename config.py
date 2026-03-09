import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'RedditDiscordBot/1.0')

MAX_POSTS_PER_SCRAPE = int(os.getenv('MAX_POSTS_PER_SCRAPE', '25'))
POST_DELAY_SECONDS = float(os.getenv('POST_DELAY_SECONDS', '2.0'))
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '8'))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

TEMP_DIR = 'temp'
LOGS_DIR = 'logs'

VALID_SORT_TYPES = ['new', 'rising', 'hot', 'top']

REQUIRED_ENV_VARS = [
    'DISCORD_BOT_TOKEN',
    'REDDIT_CLIENT_ID',
    'REDDIT_CLIENT_SECRET'
]

def validate_config():
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
    return True
