import praw
import prawcore
import logging
import asyncio
from config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    VALID_SORT_TYPES
)

logger = logging.getLogger(__name__)

class RedditClient:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        logger.info("Reddit client initialized")
    
    def _fetch_posts_sync(self, subreddit_name, sort_type, limit):
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            if sort_type == 'new':
                posts = subreddit.new(limit=limit)
            elif sort_type == 'rising':
                posts = subreddit.rising(limit=limit)
            elif sort_type == 'hot':
                posts = subreddit.hot(limit=limit)
            elif sort_type == 'top':
                posts = subreddit.top(limit=limit)
            else:
                raise ValueError(f"Invalid sort type: {sort_type}")
            
            posts_list = list(posts)
            logger.info(f"Fetched {len(posts_list)} posts from r/{subreddit_name} ({sort_type})")
            return posts_list, None
            
        except prawcore.exceptions.NotFound:
            return None, f"Subreddit r/{subreddit_name} not found"
        except prawcore.exceptions.Forbidden:
            return None, f"Access denied to r/{subreddit_name} (private or banned)"
        except prawcore.exceptions.ResponseException as e:
            if e.response.status_code == 429:
                return None, "Rate limited by Reddit. Please wait and try again."
            return None, f"Reddit API error: HTTP {e.response.status_code}"
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None, f"Unexpected error: {str(e)}"
    
    async def get_posts(self, subreddit_name, sort_type, limit):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_posts_sync, subreddit_name, sort_type, limit)
    
    def _validate_subreddit_sync(self, subreddit_name):
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            _ = subreddit.id
            return True, None
        except prawcore.exceptions.NotFound:
            return False, f"Subreddit r/{subreddit_name} not found"
        except prawcore.exceptions.Forbidden:
            return False, f"Access denied to r/{subreddit_name}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    async def validate_subreddit(self, subreddit_name):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._validate_subreddit_sync, subreddit_name)
