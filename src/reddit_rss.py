import feedparser
import logging
import re
import aiohttp
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

    def __init__(self):
        logger.info("RedditRSSClient initialized")

    def _get_rss_url(self, subreddit: str, sort_type: str) -> str:
        sort_type = sort_type.lower()
        if sort_type == 'random':
            return self.BASE_RSS_URL.format(subreddit=subreddit, sort='hot')
        if sort_type not in ['hot', 'new', 'rising', 'top', 'controversial']:
            sort_type = 'hot'
        return self.BASE_RSS_URL.format(subreddit=subreddit, sort=sort_type)

    def _extract_media_url(self, entry):
        """Extract direct media URL from RSS entry - only return if it's a direct video/image URL"""
        # Check enclosures first (common for videos/images)
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if 'href' in enc:
                    url = enc['href']
                    # Only return if it's a direct video URL (not thumbnail)
                    if any(ext in url.lower() for ext in ['.mp4', '.webm']):
                        return url

        # Check media_content
        if hasattr(entry, 'media_content') and entry.media_content:
            for media in entry.media_content:
                if 'url' in media:
                    url = media['url']
                    if any(ext in url.lower() for ext in ['.mp4', '.webm']):
                        return url

        # Parse content HTML for direct video URLs only (not thumbnails)
        content = entry.get('content', [{}])[0].get('value', '') if hasattr(entry, 'content') else ''
        if not content:
            content = entry.get('description', '')

        # Look for direct video URLs in content (v.redd.it or direct mp4)
        video_patterns = [
            r'https?://v\.redd\.it/[\w/.-]+',
            r'https?://[^\s"\']+\.mp4',
            r'https?://[^\s"\']+\.webm',
        ]

        for pattern in video_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return matches[0]

        # Return None for thumbnail-only URLs (external-preview.redd.it are thumbnails)
        return None

    async def _fetch_original_url(self, permalink: str) -> Optional[str]:
        """
        Fetch the original external URL from Reddit's .json API.
        This returns the original URL that was posted (YouTube, redgifs, etc.)
        """
        try:
            json_url = f"https://www.reddit.com{permalink}.json"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch .json for {permalink}: HTTP {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    if not data or len(data) < 2:
                        return None
                    
                    # Get the post data from the JSON response
                    post_data = data[0]['data']['children'][0]['data']
                    
                    # Get the original URL that was posted
                    original_url = post_data.get('url', '')
                    
                    # Always check for Reddit-hosted video (secure_media/media)
                    # regardless of URL format, since v.redd.it URLs also need this
                    secure_media = post_data.get('secure_media', {}) or {}
                    media = post_data.get('media', {}) or {}
                    
                    # Check for Reddit video (works for both reddit.com and v.redd.it URLs)
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
                            # Short v.redd.it URL without DASH fallback found above
                            # Return None so we fall back to yt-dlp with full Reddit URL
                            logger.warning(f"v.redd.it URL without fallback: {original_url}")
                            return None
                        else:
                            # It's an external URL - this is what we want!
                            return original_url
                    
                    # Also check for domain from permalink if no URL found
                    return None
                    
        except Exception as e:
            logger.warning(f"Error fetching .json for {permalink}: {e}")
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