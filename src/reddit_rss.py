import feedparser
import logging
import re
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

        if 'self text:' in description.lower() or 'submitted by' in description.lower():
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
                    is_self = 'selftext=' in entry.get('description', '') or '/comments/' in link
                    is_gallery = '/gallery/' in link

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
                        url=link,
                        permalink=permalink,
                        score=desc_data['score'],
                        num_comments=desc_data['num_comments'],
                        author=author,
                        created_utc=datetime.now().timestamp(),
                        is_self=is_self,
                        selftext=desc_data['selftext'],
                        over_18=desc_data['over_18'],
                        subreddit=subreddit,
                        is_gallery=is_gallery
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