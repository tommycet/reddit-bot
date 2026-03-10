import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Discord Configuration
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Reddit API Configuration
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'RedditDiscordBot/1.0')
REDDIT_USERNAME = os.getenv('REDDIT_USERNAME')
REDDIT_PASSWORD = os.getenv('REDDIT_PASSWORD')

# Bot Settings
MAX_POSTS_PER_SCRAPE = int(os.getenv('MAX_POSTS_PER_SCRAPE', '25'))
POST_DELAY_SECONDS = float(os.getenv('POST_DELAY_SECONDS', '2.0'))
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '8'))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# GIF Conversion Settings
GIF_ENABLED = os.getenv('GIF_ENABLED', 'true').lower() == 'true'
GIF_MAX_DURATION_SECONDS = int(os.getenv('GIF_MAX_DURATION_SECONDS', '60'))
GIF_WIDTH = int(os.getenv('GIF_WIDTH', '720'))
GIF_FPS = int(os.getenv('GIF_FPS', '30'))

# Video Compression Settings
VIDEO_TARGET_SIZE_MB = float(os.getenv('VIDEO_TARGET_SIZE_MB', '7.5'))
VIDEO_MAX_SIZE_MB = float(os.getenv('VIDEO_MAX_SIZE_MB', '8'))

# Rate Limiting (PRAW fallback)
PRAW_RETRY_ATTEMPTS = int(os.getenv('PRAW_RETRY_ATTEMPTS', '3'))
PRAW_BASE_DELAY_SECONDS = float(os.getenv('PRAW_BASE_DELAY_SECONDS', '5'))

# Directories
TEMP_DIR = 'temp'
LOGS_DIR = 'logs'

# Valid sort types
VALID_SORT_TYPES = ['new', 'rising', 'hot', 'top', 'controversial']

# Concurrent processing
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '3'))

# Required environment variables
REQUIRED_ENV_VARS = [
    'DISCORD_BOT_TOKEN',
    'REDDIT_CLIENT_ID',
    'REDDIT_CLIENT_SECRET'
]

# Log configuration (without exposing secrets)
logger.info("Configuration loaded from environment:")
logger.info(f" - DISCORD_BOT_TOKEN: {'Set' if DISCORD_BOT_TOKEN else 'MISSING'}")
logger.info(f" - REDDIT_CLIENT_ID: {'Set' if REDDIT_CLIENT_ID else 'MISSING'}")
logger.info(f" - REDDIT_CLIENT_SECRET: {'Set' if REDDIT_CLIENT_SECRET else 'MISSING'}")
logger.info(f" - REDDIT_USER_AGENT: {REDDIT_USER_AGENT}")
logger.info(f" - MAX_POSTS_PER_SCRAPE: {MAX_POSTS_PER_SCRAPE}")
logger.info(f" - MAX_FILE_SIZE_MB: {MAX_FILE_SIZE_MB}")
logger.info(f" - GIF_ENABLED: {GIF_ENABLED}")
logger.info(f" - GIF_MAX_DURATION_SECONDS: {GIF_MAX_DURATION_SECONDS}s")

def validate_config():
    """Validate required environment variables"""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
    return True
