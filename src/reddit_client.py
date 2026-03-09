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
        logger.info("Initializing PRAW Reddit client...")
        logger.info(f"  - Client ID: {REDDIT_CLIENT_ID}")
        logger.info(f"  - Client Secret: {REDDIT_CLIENT_SECRET[:10]}...{REDDIT_CLIENT_SECRET[-5:]}")
        logger.info(f"  - User Agent: {REDDIT_USER_AGENT}")
        
        self.reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        
        try:
            logger.info("Testing Reddit API connection...")
            test_subreddit = self.reddit.subreddit('announcements')
            logger.info(f"  - Connection test successful (r/announcements ID: {test_subreddit.id})")
        except Exception as e:
            logger.warning(f"  - Connection test failed: {e}")
        
        logger.info("Reddit client initialized successfully")
    
    def _fetch_posts_sync(self, subreddit_name, sort_type, limit):
        try:
            logger.info(f"Attempting to fetch {limit} posts from r/{subreddit_name} (sort: {sort_type})")
            logger.info(f"Reddit client auth: client_id={REDDIT_CLIENT_ID[:10]}..., user_agent={REDDIT_USER_AGENT}")
            
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
            logger.info(f"SUCCESS: Fetched {len(posts_list)} posts from r/{subreddit_name} ({sort_type})")
            return posts_list, None

        except prawcore.exceptions.NotFound:
            logger.error(f"ERROR: Subreddit r/{subreddit_name} not found (404)")
            return None, f"Subreddit r/{subreddit_name} not found"
        except prawcore.exceptions.Forbidden as e:
            logger.error(f"ERROR: Access denied to r/{subreddit_name}")
            logger.error(f"  - Exception type: {type(e).__name__}")
            logger.error(f"  - Exception message: {str(e)}")
            logger.error(f"  - Response status: {getattr(e, 'response', None)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"  - Response status code: {e.response.status_code}")
                logger.error(f"  - Response headers: {e.response.headers}")
                try:
                    logger.error(f"  - Response body: {e.response.text}")
                except:
                    pass
            logger.error(f"  - This could mean: subreddit is private, banned, or requires special authentication")
            return None, f"Access denied to r/{subreddit_name} (private or banned)"
        except prawcore.exceptions.ResponseException as e:
            logger.error(f"ERROR: Reddit API Response Exception")
            logger.error(f"  - HTTP Status: {e.response.status_code}")
            logger.error(f"  - Response: {e.response}")
            if e.response.status_code == 429:
                return None, "Rate limited by Reddit. Please wait and try again."
            return None, f"Reddit API error: HTTP {e.response.status_code}"
        except prawcore.exceptions.PrawcoreException as e:
            logger.error(f"ERROR: PRAW Core Exception")
            logger.error(f"  - Exception type: {type(e).__name__}")
            logger.error(f"  - Exception message: {str(e)}")
            return None, f"Reddit API error: {str(e)}"
        except Exception as e:
            logger.error(f"ERROR: Unexpected error fetching posts from r/{subreddit_name}")
            logger.error(f"  - Exception type: {type(e).__name__}")
            logger.error(f"  - Exception message: {str(e)}")
            import traceback
            logger.error(f"  - Traceback: {traceback.format_exc()}")
            return None, f"Unexpected error: {str(e)}"
    
    async def get_posts(self, subreddit_name, sort_type, limit):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_posts_sync, subreddit_name, sort_type, limit)
    
    def _validate_subreddit_sync(self, subreddit_name):
        try:
            logger.info(f"Validating subreddit: r/{subreddit_name}")
            logger.info(f"  - Client ID: {REDDIT_CLIENT_ID[:10]}...")
            logger.info(f"  - User Agent: {REDDIT_USER_AGENT}")
            
            subreddit = self.reddit.subreddit(subreddit_name)
            subreddit_id = subreddit.id
            logger.info(f"SUCCESS: r/{subreddit_name} validated (ID: {subreddit_id})")
            return True, None
        except prawcore.exceptions.NotFound:
            logger.error(f"ERROR: Subreddit r/{subreddit_name} not found (404)")
            return False, f"Subreddit r/{subreddit_name} not found"
        except prawcore.exceptions.Forbidden as e:
            logger.error(f"ERROR: Access denied to r/{subreddit_name}")
            logger.error(f"  - Exception type: {type(e).__name__}")
            logger.error(f"  - Exception message: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"  - Response status code: {e.response.status_code}")
                logger.error(f"  - Response headers: {e.response.headers}")
                try:
                    logger.error(f"  - Response body: {e.response.text}")
                except:
                    pass
            logger.error(f"  - Possible causes: private subreddit, banned, or authentication issue")
            return False, f"Access denied to r/{subreddit_name}"
        except Exception as e:
            logger.error(f"ERROR: Unexpected error validating r/{subreddit_name}")
            logger.error(f"  - Exception type: {type(e).__name__}")
            logger.error(f"  - Exception message: {str(e)}")
            import traceback
            logger.error(f"  - Traceback: {traceback.format_exc()}")
            return False, f"Unexpected error: {str(e)}"
    
    async def validate_subreddit(self, subreddit_name):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._validate_subreddit_sync, subreddit_name)
