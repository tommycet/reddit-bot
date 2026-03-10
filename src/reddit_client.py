import praw
import prawcore
import logging
import asyncio
import random
import time
from datetime import datetime, timedelta
from config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    VALID_SORT_TYPES
)
from src.reddit_rss import RedditRSSClient

logger = logging.getLogger(__name__)

# Cache for subreddit validation (1 hour TTL)
subreddit_cache = {}
CACHE_TTL_SECONDS = 3600

class RedditPRAWClient:
    """PRAW-based Reddit client with retry logic"""
    
    def __init__(self):
        logger.info("Initializing PRAW Reddit client...")
        logger.info(f" - Client ID: {REDDIT_CLIENT_ID}")
        logger.info(f" - Client Secret: {REDDIT_CLIENT_SECRET[:10]}...{REDDIT_CLIENT_SECRET[-5:]}")
        logger.info(f" - User Agent: {REDDIT_USER_AGENT}")
        
        self.reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        
        self.retry_attempts = 3
        self.base_delay = 5  # seconds
        
        try:
            logger.info("Testing Reddit API connection...")
            test_subreddit = self.reddit.subreddit('announcements')
            logger.info(f" - Connection test successful (r/announcements ID: {test_subreddit.id})")
        except Exception as e:
            logger.warning(f" - Connection test failed: {e}")
        
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
    
    async def fetch_with_retry(self, subreddit_name, sort_type, limit):
        """Fetch posts with exponential backoff retry logic"""
        for attempt in range(self.retry_attempts):
            posts, error = self._fetch_posts_sync(subreddit_name, sort_type, limit)
            
            if error and "Rate limited" in error:
                if attempt < self.retry_attempts - 1:
                    delay = self.base_delay * (2 ** attempt) + random.uniform(1, 3)
                    logger.warning(f"Rate limited, waiting {delay:.1f}s before retry {attempt+1}/{self.retry_attempts}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Rate limited after {self.retry_attempts} attempts")
                    return None, "Rate limited after all retries"
            
            return posts, error
        
        return None, "All retry attempts failed"
    
    async def validate_subreddit(self, subreddit_name):
        """Validate subreddit using PRAW"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._validate_subreddit_sync, subreddit_name)
    
    def _validate_subreddit_sync(self, subreddit_name):
        try:
            logger.info(f"Validating subreddit: r/{subreddit_name} (PRAW)")
            logger.info(f" - Client ID: {REDDIT_CLIENT_ID[:10]}...")
            logger.info(f" - User Agent: {REDDIT_USER_AGENT}")
            
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


class RedditHybridClient:
    """Hybrid Reddit client using RSS (primary) and PRAW (fallback)"""
    
    def __init__(self):
        logger.info("Initializing RedditHybridClient...")
        self.rss_client = RedditRSSClient()
        self.praw_client = RedditPRAWClient()
        logger.info("RedditHybridClient initialized (RSS primary, PRAW fallback)")
    
    def _is_subreddit_cached(self, subreddit_name):
        """Check if subreddit is in cache and not expired"""
        if subreddit_name in subreddit_cache:
            cached = subreddit_cache[subreddit_name]
            if datetime.now() < cached['expires_at']:
                logger.info(f"Subreddit cache HIT: r/{subreddit_name}")
                return True
            else:
                logger.info(f"Subreddit cache EXPIRED: r/{subreddit_name}")
                del subreddit_cache[subreddit_name]
        return False
    
    def _cache_subreddit(self, subreddit_name, valid=True):
        """Add subreddit to cache"""
        subreddit_cache[subreddit_name] = {
            'valid': valid,
            'timestamp': datetime.now(),
            'expires_at': datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)
        }
        logger.info(f"Subreddit cached: r/{subreddit_name} (valid={valid}, TTL={CACHE_TTL_SECONDS}s)")
    
    async def get_posts(self, subreddit_name, sort_type, limit):
        """
        Get posts using RSS first, fallback to PRAW
        
        Args:
            subreddit_name: Subreddit name (without r/)
            sort_type: Sort type (hot, new, rising, top)
            limit: Number of posts to fetch
            
        Returns:
            Tuple of (posts_list, error_message)
        """
        logger.info(f"Fetching posts: r/{subreddit_name} | sort={sort_type} | limit={limit}")
        
        # Step 1: Try RSS first (primary method)
        logger.info(f"Attempting RSS fetch for r/{subreddit_name}...")
        posts, error = await self.rss_client.fetch_posts(subreddit_name, sort_type, limit)
        
        if not error and posts:
            logger.info(f"RSS fetch successful: {len(posts)} posts from r/{subreddit_name}")
            return posts, None
        
        # Step 2: RSS failed, fallback to PRAW
        logger.warning(f"RSS failed for r/{subreddit_name}: {error}")
        logger.info(f"Falling back to PRAW for r/{subreddit_name}...")
        
        posts, error = await self.praw_client.fetch_with_retry(subreddit_name, sort_type, limit)
        
        if posts:
            logger.info(f"PRAW fallback successful: {len(posts)} posts from r/{subreddit_name}")
        else:
            logger.error(f"PRAW fallback failed for r/{subreddit_name}: {error}")
        
        return posts, error
    
    async def validate_subreddit(self, subreddit_name):
        """
        Validate subreddit using RSS first, fallback to PRAW
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        logger.info(f"Validating subreddit: r/{subreddit_name}")
        
        # Check cache first
        if self._is_subreddit_cached(subreddit_name):
            cached = subreddit_cache.get(subreddit_name, {})
            if cached.get('valid'):
                return True, None
            else:
                return False, "Subreddit previously invalid"
        
        # Step 1: Try RSS validation
        logger.info(f"Attempting RSS validation for r/{subreddit_name}...")
        is_valid, error = await self.rss_client.validate_subreddit(subreddit_name)
        
        if is_valid:
            logger.info(f"RSS validation successful for r/{subreddit_name}")
            self._cache_subreddit(subreddit_name, valid=True)
            return True, None
        
        # Step 2: RSS validation failed, try PRAW
        logger.warning(f"RSS validation failed for r/{subreddit_name}: {error}")
        logger.info(f"Falling back to PRAW validation for r/{subreddit_name}...")
        
        is_valid, error = await self.praw_client.validate_subreddit(subreddit_name)
        
        if is_valid:
            logger.info(f"PRAW validation successful for r/{subreddit_name}")
            self._cache_subreddit(subreddit_name, valid=True)
            return True, None
        
        # Both failed
        logger.error(f"Both RSS and PRAW validation failed for r/{subreddit_name}: {error}")
        self._cache_subreddit(subreddit_name, valid=False)
        return False, error


# Backward compatibility alias
RedditClient = RedditHybridClient
