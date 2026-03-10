import feedparser
import logging
import re
import asyncio
import aiohttp
import time
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RSSPost:
    title: str
    url: str
    permalink: str
    score: int
    num_comments: int
    author: str
    created_utc: float
    is_self: bool
    selftext: str
    subreddit: str
    over_18: bool = False
    is_gallery: bool = False
    gallery_data: Optional[dict] = None
    media_metadata: Optional[dict] = None

    @property
    def id(self) -> str:
        match = re.search(r'/comments/(\w+)/', self.permalink)
        if match:
            return match.group(1)
        return ""

    @property
    def author_name(self) -> str:
        return self.author if self.author else '[deleted]'


class RedditRSSClient:
    BASE_RSS_URL = "https://www.reddit.com/r/{subreddit}/{sort}.rss"

    def __init__(self, praw_reddit=None, reddit_credentials=None):
        self.praw_reddit = praw_reddit
        
        # OAuth2 credentials for password-based auth fallback
        self._oauth_token = None
        self._oauth_token_expiry = 0
        self._reddit_creds = reddit_credentials or {}
        
        has_oauth = all(self._reddit_creds.get(k) for k in ['client_id', 'client_secret', 'username', 'password'])
        logger.info("RedditRSSClient initialized (PRAW fallback: %s, OAuth fallback: %s)",
                    'enabled' if praw_reddit else 'disabled',
                    'enabled' if has_oauth else 'disabled')

    def _get_rss_url(self, subreddit: str, sort_type: str) -> str:
        sort_type = sort_type.lower()
        if sort_type == 'random':
            return self.BASE_RSS_URL.format(subreddit=subreddit, sort='hot')
        if sort_type not in ['hot', 'new', 'rising', 'top', 'controversial']:
            sort_type = 'hot'
        return self.BASE_RSS_URL.format(subreddit=subreddit, sort=sort_type)

    def _extract_media_url(self, entry):
        """Extract direct media URL from RSS entry - videos and images"""
        # Check enclosures first (common for videos/images)
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if 'href' in enc:
                    url = enc['href']
                    if any(ext in url.lower() for ext in ['.mp4', '.webm', '.jpg', '.jpeg', '.png', '.gif']):
                        return url

        # Check media_content
        if hasattr(entry, 'media_content') and entry.media_content:
            for media in entry.media_content:
                if 'url' in media:
                    url = media['url']
                    if any(ext in url.lower() for ext in ['.mp4', '.webm', '.jpg', '.jpeg', '.png', '.gif']):
                        return url

        # Parse content HTML for direct media URLs (not thumbnails)
        content = entry.get('content', [{}])[0].get('value', '') if hasattr(entry, 'content') else ''
        if not content:
            content = entry.get('description', '')

        # Look for direct media URLs in content
        media_patterns = [
            r'https?://i\.redd\.it/[\w/.-]+\.(?:jpg|jpeg|png|gif)',
            r'https?://v\.redd\.it/[\w/.-]+',
            r'https?://[^\s"\']+\.mp4',
            r'https?://[^\s"\']+\.webm',
        ]

        for pattern in media_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Skip thumbnail URLs (external-preview.redd.it are thumbnails)
                for match in matches:
                    if 'external-preview.redd.it' not in match and 'preview.redd.it' not in match:
                        return match

        # Return None if no direct media URL found
        return None

    async def _fetch_original_url(self, permalink: str) -> Optional[str]:
        """
        Fetch the original external URL with triple fallback:
        1. Unauthenticated .json API (fast, works for most posts)
        2. PRAW authenticated client (handles NSFW, requires PRAW setup)
        3. OAuth2 password grant (handles NSFW, uses username/password)
        """
        # Try 1: Unauthenticated .json API
        result = await self._fetch_original_url_json(permalink)
        if result:
            return result
        
        # Try 2: PRAW (authenticated)
        if self.praw_reddit:
            result = await self._fetch_original_url_praw(permalink)
            if result:
                return result
        
        # Try 3: OAuth2 password grant (authenticated)
        if self._reddit_creds:
            result = await self._fetch_original_url_oauth(permalink)
            if result:
                return result
        
        return None
    
    async def _fetch_original_url_json(self, permalink: str) -> Optional[str]:
        """Try the unauthenticated .json API first"""
        try:
            json_url = f"https://www.reddit.com{permalink}.json"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.warning(f".json API failed for {permalink}: HTTP {response.status}")
                        return None
                    
                    data = await response.json()
                    return self._parse_post_data(data, permalink)
                    
        except Exception as e:
            logger.warning(f"Error fetching .json for {permalink}: {e}")
            return None
    
    async def _fetch_original_url_praw(self, permalink: str) -> Optional[str]:
        """Fallback: use authenticated PRAW to get the submission URL (handles NSFW)"""
        try:
            logger.info(f"Using PRAW fallback for {permalink}")
            loop = asyncio.get_event_loop()
            
            def fetch_with_praw():
                try:
                    submission = self.praw_reddit.submission(url=f"https://www.reddit.com{permalink}")
                    url = submission.url
                    
                    # Check for gallery post
                    if hasattr(submission, 'is_gallery') and submission.is_gallery:
                        media_metadata = getattr(submission, 'media_metadata', {}) or {}
                        gallery_data = getattr(submission, 'gallery_data', None)
                        if gallery_data and 'items' in gallery_data:
                            for item in gallery_data['items']:
                                media_id = item.get('media_id')
                                if media_id and media_id in media_metadata:
                                    media_info = media_metadata[media_id]
                                    if 's' in media_info and 'u' in media_info['s']:
                                        img_url = media_info['s']['u'].replace('&amp;', '&')
                                        logger.info(f"PRAW found gallery image: {img_url}")
                                        return img_url
                        # Fallback: try any image in media_metadata
                        for mid, minfo in media_metadata.items():
                            if 's' in minfo and 'u' in minfo['s']:
                                img_url = minfo['s']['u'].replace('&amp;', '&')
                                logger.info(f"PRAW found gallery image (fallback): {img_url}")
                                return img_url
                    
                    # Check for Reddit video
                    if hasattr(submission, 'media') and submission.media:
                        reddit_video = submission.media.get('reddit_video', {})
                        if reddit_video:
                            fallback_url = reddit_video.get('fallback_url')
                            if fallback_url:
                                logger.info(f"PRAW found DASH fallback URL: {fallback_url}")
                                return fallback_url
                    
                    if hasattr(submission, 'secure_media') and submission.secure_media:
                        reddit_video = submission.secure_media.get('reddit_video', {})
                        if reddit_video:
                            fallback_url = reddit_video.get('fallback_url')
                            if fallback_url:
                                logger.info(f"PRAW found DASH fallback URL: {fallback_url}")
                                return fallback_url
                    
                    # Return the URL if it's not a Reddit link
                    if url and not url.startswith('https://www.reddit.com'):
                        logger.info(f"PRAW found original URL: {url}")
                        return url
                    
                    return None
                except Exception as e:
                    logger.warning(f"PRAW submission fetch failed: {e}")
                    return None
            
            return await loop.run_in_executor(None, fetch_with_praw)
            
        except Exception as e:
            logger.warning(f"PRAW fallback error for {permalink}: {e}")
            return None

    async def _get_oauth_token(self) -> Optional[str]:
        """Get or refresh OAuth2 access token using password grant"""
        # Return cached token if still valid
        if self._oauth_token and time.time() < self._oauth_token_expiry:
            return self._oauth_token
        
        client_id = self._reddit_creds.get('client_id')
        client_secret = self._reddit_creds.get('client_secret')
        username = self._reddit_creds.get('username')
        password = self._reddit_creds.get('password')
        user_agent = self._reddit_creds.get('user_agent', 'RedditDiscordBot/1.0')
        
        if not all([client_id, client_secret, username, password]):
            return None
        
        try:
            auth = aiohttp.BasicAuth(client_id, client_secret)
            headers = {'User-Agent': user_agent}
            data = {
                'grant_type': 'password',
                'username': username,
                'password': password,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://www.reddit.com/api/v1/access_token',
                    auth=auth,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"OAuth token request failed: HTTP {response.status}")
                        return None
                    
                    token_data = await response.json()
                    
                    if 'access_token' not in token_data:
                        logger.warning(f"OAuth token response missing access_token: {token_data.get('error', 'unknown')}")
                        return None
                    
                    self._oauth_token = token_data['access_token']
                    # Cache for 50 minutes (tokens last 60 min)
                    self._oauth_token_expiry = time.time() + 3000
                    logger.info("OAuth2 access token obtained successfully")
                    return self._oauth_token
                    
        except Exception as e:
            logger.warning(f"OAuth token error: {e}")
            return None

    async def _fetch_original_url_oauth(self, permalink: str) -> Optional[str]:
        """Fallback: use OAuth2 password auth to access the Reddit API (handles NSFW)"""
        try:
            token = await self._get_oauth_token()
            if not token:
                return None
            
            logger.info(f"Using OAuth2 auth for {permalink}")
            # Use oauth.reddit.com with Bearer token (authenticated endpoint)
            json_url = f"https://oauth.reddit.com{permalink}.json"
            headers = {
                'Authorization': f'Bearer {token}',
                'User-Agent': self._reddit_creds.get('user_agent', 'RedditDiscordBot/1.0'),
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 401:
                        # Token expired, clear cache and retry once
                        logger.warning("OAuth token expired, refreshing...")
                        self._oauth_token = None
                        self._oauth_token_expiry = 0
                        token = await self._get_oauth_token()
                        if not token:
                            return None
                        headers['Authorization'] = f'Bearer {token}'
                        async with session.get(json_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as retry_response:
                            if retry_response.status != 200:
                                logger.warning(f"OAuth retry failed for {permalink}: HTTP {retry_response.status}")
                                return None
                            data = await retry_response.json()
                            return self._parse_post_data(data, permalink)
                    
                    if response.status != 200:
                        logger.warning(f"OAuth .json API failed for {permalink}: HTTP {response.status}")
                        return None
                    
                    data = await response.json()
                    return self._parse_post_data(data, permalink)
                    
        except Exception as e:
            logger.warning(f"OAuth fallback error for {permalink}: {e}")
            return None

    def _parse_post_data(self, data, permalink: str) -> Optional[str]:
        """Parse post data from .json API response"""
        if not data or len(data) < 2:
            return None
        
        post_data = data[0]['data']['children'][0]['data']
        original_url = post_data.get('url', '')
        
        # Check for gallery post — extract first image
        if post_data.get('is_gallery'):
            media_metadata = post_data.get('media_metadata', {}) or {}
            gallery_data = post_data.get('gallery_data', {}) or {}
            if gallery_data and 'items' in gallery_data:
                for item in gallery_data['items']:
                    media_id = item.get('media_id')
                    if media_id and media_id in media_metadata:
                        media_info = media_metadata[media_id]
                        if 's' in media_info and 'u' in media_info['s']:
                            img_url = media_info['s']['u'].replace('&amp;', '&')
                            logger.info(f"Found gallery image: {img_url}")
                            return img_url
            # Fallback: try any image in media_metadata
            for mid, minfo in media_metadata.items():
                if 's' in minfo and 'u' in minfo['s']:
                    img_url = minfo['s']['u'].replace('&amp;', '&')
                    logger.info(f"Found gallery image (fallback): {img_url}")
                    return img_url
            logger.warning(f"Gallery post but no images found in metadata")
            return None
        
        # Always check for Reddit-hosted video (secure_media/media)
        secure_media = post_data.get('secure_media', {}) or {}
        media = post_data.get('media', {}) or {}
        
        # Check for Reddit video
        reddit_video = secure_media.get('reddit_video') or media.get('reddit_video')
        if reddit_video:
            fallback_url = reddit_video.get('fallback_url')
            if fallback_url:
                logger.info(f"Found DASH fallback URL: {fallback_url}")
                return fallback_url
        
        if original_url:
            if original_url.startswith('https://www.reddit.com'):
                # Check for embedded media (YouTube, etc.)
                oembed = secure_media.get('oembed') or media.get('oembed')
                if oembed:
                    provider_url = oembed.get('provider_url', '')
                    if 'youtube' in provider_url.lower():
                        return oembed.get('url')
                return None
            elif 'v.redd.it' in original_url:
                logger.warning(f"v.redd.it URL without fallback: {original_url}")
                return None
            else:
                # External URL (i.redd.it, youtube, redgifs, etc.)
                return original_url
        
        return None

    def _parse_description(self, description: str) -> dict:
        data = {
            'score': 0,
            'num_comments': 0,
            'selftext': '',
            'is_self': False,
            'over_18': False
        }

        if not description:
            return data

        score_match = re.search(r'(\d+(?:\.\d+)?[kM]?)\s*points?', description, re.IGNORECASE)
        if score_match:
            score_str = score_match.group(1).lower()
            try:
                if 'k' in score_str:
                    data['score'] = int(float(score_str.replace('k', '')) * 1000)
                elif 'm' in score_str:
                    data['score'] = int(float(score_str.replace('m', '')) * 1000000)
                else:
                    data['score'] = int(float(score_str))
            except ValueError:
                pass

        comments_match = re.search(r'(\d+(?:\.\d+)?[kM]?)\s*comments?', description, re.IGNORECASE)
        if comments_match:
            comments_str = comments_match.group(1).lower()
            try:
                if 'k' in comments_str:
                    data['num_comments'] = int(float(comments_str.replace('k', '')) * 1000)
                elif 'm' in comments_str:
                    data['num_comments'] = int(float(comments_str.replace('m', '')) * 1000000)
                else:
                    data['num_comments'] = int(float(comments_str))
            except ValueError:
                pass

        # Only check for actual self-text indicators
        # 'submitted by' is in ALL Reddit RSS entries, so it's NOT a valid self-post indicator
        if 'self text:' in description.lower() or '<!-- sc_off -->' in description.lower():
            data['is_self'] = True
        selftext_match = re.search(r'self text:\s*(.*?)(?:<br/>|$)', description, re.DOTALL)
        if selftext_match:
            data['selftext'] = selftext_match.group(1).strip()[:2000]

        if '[nsfw]' in description.lower():
            data['over_18'] = True

        return data

    async def fetch_posts(self, subreddit: str, sort_type: str, limit: int = 10) -> Tuple[List[RSSPost], Optional[str]]:
        try:
            rss_url = self._get_rss_url(subreddit, sort_type)
            logger.info(f"Fetching RSS from: {rss_url}")

            feed = feedparser.parse(rss_url)

            if feed.bozo:
                logger.warning(f"RSS feed parsing issue: {feed.bozo_exception}")

            if 'status' in feed:
                status = feed.status
                if status == 403:
                    return [], f"Access denied to r/{subreddit} (private or banned)"
                elif status == 404:
                    return [], f"Subreddit r/{subreddit} not found"
                elif status >= 500:
                    return [], f"Reddit server error: {status}"

            if not feed.entries:
                return [], f"No posts found in r/{subreddit}"

            posts = []
            for entry in feed.entries[:limit]:
                try:
                    desc_data = self._parse_description(entry.get('description', ''))
                    link = entry.get('link', '')
                    permalink = link.replace('https://www.reddit.com', '')

                    # Extract actual media URL from the entry
                    media_url = self._extract_media_url(entry)
                    
                    # Try to get original external URL from Reddit's .json API
                    original_url = await self._fetch_original_url(permalink)
                    
                    # Determine is_self: true only if no media URL was found anywhere
                    # '/comments/' is in ALL Reddit links, so it can't be used as an indicator
                    has_media = (media_url is not None) or (original_url is not None)
                    is_self = desc_data.get('is_self', False) and not has_media
                    
                    # Check if it's a gallery
                    is_gallery = '/gallery/' in link

                    if original_url:
                        logger.info(f"Found original URL for {permalink}: {original_url}")
                        url = original_url
                    elif media_url:
                        # Fall back to RSS media URL if no original URL found
                        url = media_url
                    else:
                        # Use Reddit post link as last resort
                        url = link
                    
                    logger.info(f"RSS Post: link={link}, is_self={is_self}, original_url={original_url}, media_url={media_url}, final_url={url}")

                    author = entry.get('author', '[deleted]')
                    if 'submitted by' in entry.get('description', ''):
                        author_match = re.search(r'submitted by\s+/u/(\w+)', entry.get('description', ''))
                        if author_match:
                            author = author_match.group(1)

                    if sort_type == 'random':
                        import random
                        posts_list = list(feed.entries)
                        random.shuffle(posts_list)
                        entry = random.choice(posts_list[:min(limit * 2, len(posts_list))])

                    post = RSSPost(
                        title=entry.get('title', ''),
                        url=url,
                        permalink=permalink,
                        score=desc_data['score'],
                        num_comments=desc_data['num_comments'],
                        author=author,
                        created_utc=datetime.now().timestamp(),
                        is_self=is_self,
                        selftext=desc_data['selftext'],
                        over_18=desc_data['over_18'],
                        subreddit=subreddit,
                        is_gallery=is_gallery,
                        gallery_data=entry.get('media_metadata', {}),
                        media_metadata=entry.get('media_metadata', {})
                    )
                    posts.append(post)

                except Exception as e:
                    logger.error(f"Error parsing RSS entry: {e}")
                    continue

            if sort_type == 'random' and posts:
                posts = [random.choice(posts)]

            logger.info(f"Successfully fetched {len(posts)} posts from r/{subreddit} via RSS")
            return posts, None

        except Exception as e:
            logger.error(f"Error fetching RSS feed: {e}")
            return [], f"RSS fetch error: {str(e)}"

    async def validate_subreddit(self, subreddit: str) -> Tuple[bool, Optional[str]]:
        try:
            posts, error = await self.fetch_posts(subreddit, 'hot', limit=1)
            if error:
                return False, error
            if not posts:
                return False, f"No posts found in r/{subreddit}"
            return True, None
        except Exception as e:
            logger.error(f"Error validating subreddit via RSS: {e}")
            return False, f"Validation error: {str(e)}"