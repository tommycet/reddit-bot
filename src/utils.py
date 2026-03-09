import os
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def ensure_temp_dir():
    Path('temp').mkdir(exist_ok=True)

def clean_temp_files():
    temp_dir = Path('temp')
    if temp_dir.exists():
        for file in temp_dir.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                    logger.info(f"Deleted temp file: {file}")
                except Exception as e:
                    logger.error(f"Failed to delete {file}: {e}")

async def delete_file(filepath):
    if filepath and os.path.exists(filepath):
        try:
            await asyncio.sleep(0.1)
            os.remove(filepath)
            logger.info(f"Deleted file: {filepath}")
        except Exception as e:
            logger.error(f"Failed to delete {filepath}: {e}")

def validate_sort_type(sort_type):
    return sort_type.lower() in ['new', 'rising', 'hot', 'top']

def validate_post_count(count):
    try:
        count = int(count)
        return 1 <= count <= 25, count
    except ValueError:
        return False, 0

def format_number(num):
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    return str(num)

def truncate_text(text, max_length=4000):
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def get_file_extension(url):
    if not url:
        return None
    url_lower = url.lower().split('?')[0]
    for ext in ['.mp4', '.webm', '.gif', '.jpg', '.jpeg', '.png']:
        if url_lower.endswith(ext):
            return ext
    return '.mp4'

def is_adult_content(post):
    return post.over_18 or post.subreddit.over18

def setup_logging():
    import logging.config

    Path('logs').mkdir(exist_ok=True)
    Path('temp').mkdir(exist_ok=True)

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
            'detailed': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s\n  -> File: %(filename)s:%(lineno)d\n  -> Function: %(funcName)s'
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'detailed',
                'level': 'DEBUG',
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': 'logs/bot.log',
                'formatter': 'detailed',
                'level': 'DEBUG',
            },
        },
        'root': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
    })
