import asyncio
import logging
from typing import List, Set, Optional
from dataclasses import dataclass
from src.database import db
from src.reddit_client import RedditClient
from src.media_downloader import download_media
from src.post_formatter import create_post_embed
import discord
import os
import time

logger = logging.getLogger(__name__)


@dataclass
class ScrapingState:
    """Tracks state for continuous scraping of a subreddit"""

    subreddit: str
    sort_type: str
    last_post_timestamp: Optional[float] = (
        None  # For time-based sorts (new, hot, rising)
    )
    page_offset: int = 0  # For static sorts (top, controversial)
    consecutive_empty: int = 0
    total_sent: int = 0


class ScraperManager:
    def __init__(self):
        self._reddit_client = None
        self.active_tasks: Set[asyncio.Task] = set()
        self.is_running = False
        self.lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self.subreddit_states: dict = {}  # Maps "subreddit:sort" -> ScrapingState

    @property
    def reddit_client(self):
        """Lazy initialization of Reddit client"""
        if self._reddit_client is None:
            self._reddit_client = RedditClient()
        return self._reddit_client

    def _is_time_based_sort(self, sort_type: str) -> bool:
        """Check if sort type is time-based (gets new posts over time)"""
        return sort_type.lower() in ["new", "hot", "rising"]

    def _is_static_sort(self, sort_type: str) -> bool:
        """Check if sort type is static (fixed set, need pagination)"""
        return sort_type.lower() in ["top", "controversial"]

    async def start_continuous_scrape(
        self,
        subreddits: List[str],
        sort_type: str,
        channel: discord.TextChannel,
        batch_size: int = 5,
        delay_seconds: float = 2.0,
        poll_interval: float = 30.0,
    ):
        """Start continuous scraping for multiple subreddits in round-robin

        Args:
            subreddits: List of subreddit names
            sort_type: Sort type (hot, new, rising, top, controversial)
            channel: Discord channel to send posts to
            batch_size: Number of posts to fetch per batch per subreddit
            delay_seconds: Seconds between individual post sends
            poll_interval: Seconds to wait between polling cycles when no new posts
        """
        async with self.lock:
            if self.is_running:
                return (
                    False,
                    "Scraper is already running. Stop it first with /scrape-continuous-stop",
                )

            self.is_running = True
            self._stop_event.clear()

            # Normalize subreddit names
            subreddits = [
                s.lower().strip().lstrip("r/").lstrip("/r/") for s in subreddits
            ]

            # Initialize state for each subreddit
            self.subreddit_states = {}
            for subreddit in subreddits:
                key = f"{subreddit}:{sort_type.lower()}"
                # Try to resume from database
                last_post = db.get_last_scraped_post(subreddit, sort_type)
                last_timestamp = last_post[1] if last_post else None

                self.subreddit_states[key] = ScrapingState(
                    subreddit=subreddit,
                    sort_type=sort_type.lower(),
                    last_post_timestamp=last_timestamp,
                    page_offset=0,
                    consecutive_empty=0,
                    total_sent=0,
                )

                # Mark as active in database
                db.start_session(subreddit, sort_type)
                logger.info(
                    f"Started continuous scrape for r/{subreddit} ({sort_type}) from timestamp: {last_timestamp}"
                )

            # Create and track the task
            task = asyncio.create_task(
                self._continuous_scrape_loop(
                    subreddits,
                    sort_type,
                    channel,
                    batch_size,
                    delay_seconds,
                    poll_interval,
                )
            )
            self.active_tasks.add(task)
            task.add_done_callback(lambda t: self.active_tasks.discard(t))

            return (
                True,
                f"Started continuous scraping for {len(subreddits)} subreddit(s): {', '.join(subreddits)}. Run until you stop it!",
            )

    async def stop_all_scraping(self):
        """Stop all active scraping tasks"""
        async with self.lock:
            self.is_running = False
            self._stop_event.set()

            # Cancel all active tasks
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to finish (with timeout)
            if self.active_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.active_tasks, return_exceptions=True),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for tasks to cancel")

            self.active_tasks.clear()

            # Stop all database sessions
            for key, state in self.subreddit_states.items():
                db.stop_session(state.subreddit, state.sort_type)

            self.subreddit_states.clear()

            return True, "Stopped all continuous scraping tasks"

    def get_status(self) -> List[dict]:
        """Get status of all active scraping sessions"""
        sessions = db.get_active_sessions()
        status_list = []

        # Add active states from current session
        for key, state in self.subreddit_states.items():
            stored_count = db.get_scraped_count(state.subreddit, state.sort_type)
            status_list.append(
                {
                    "subreddit": state.subreddit,
                    "sort_type": state.sort_type,
                    "total_sent_this_session": state.total_sent,
                    "total_tracked": stored_count,
                    "last_post_timestamp": state.last_post_timestamp,
                    "consecutive_empty": state.consecutive_empty,
                    "is_running": self.is_running,
                }
            )

        # Add any database sessions not in current active set
        for subreddit, sort_type, started_at, total_scraped in sessions:
            key = f"{subreddit}:{sort_type}"
            if key not in self.subreddit_states:
                stored_count = db.get_scraped_count(subreddit, sort_type)
                status_list.append(
                    {
                        "subreddit": subreddit,
                        "sort_type": sort_type,
                        "total_sent_this_session": 0,
                        "total_tracked": stored_count,
                        "last_post_timestamp": None,
                        "consecutive_empty": 0,
                        "is_running": False,
                    }
                )

        return status_list

    async def _continuous_scrape_loop(
        self,
        subreddits: List[str],
        sort_type: str,
        channel: discord.TextChannel,
        batch_size: int,
        delay_seconds: float,
        poll_interval: float,
    ):
        """Main continuous scraping loop - runs indefinitely until stopped"""
        logger.info(
            f"Starting continuous scrape loop for: {subreddits} (sort: {sort_type})"
        )

        current_idx = 0

        try:
            while self.is_running and not self._stop_event.is_set():
                subreddit = subreddits[current_idx]
                key = f"{subreddit}:{sort_type.lower()}"
                state = self.subreddit_states.get(key)

                if not state:
                    logger.error(f"No state found for {key}")
                    current_idx = (current_idx + 1) % len(subreddits)
                    continue

                # Check if we should stop (handled via stop command)
                if self._stop_event.is_set():
                    break

                # Fetch posts based on sort type
                posts = []

                if self._is_time_based_sort(sort_type):
                    # For new/hot/rising: fetch recent posts
                    posts, error = await self._fetch_time_based_posts(state, batch_size)
                else:
                    # For top/controversial: fetch with pagination
                    posts, error = await self._fetch_static_posts(state, batch_size)

                if error:
                    logger.error(f"Error fetching from r/{subreddit}: {error}")
                    state.consecutive_empty += 1
                    await asyncio.sleep(poll_interval)
                    current_idx = (current_idx + 1) % len(subreddits)
                    continue

                if not posts:
                    logger.debug(
                        f"No new posts from r/{subreddit} (consecutive empty: {state.consecutive_empty})"
                    )
                    state.consecutive_empty += 1

                    # For time-based sorts, wait before polling again
                    if self._is_time_based_sort(sort_type):
                        logger.info(
                            f"No new posts from r/{subreddit}, waiting {poll_interval}s before next poll..."
                        )
                        # Wait in small increments to check for stop signal
                        for _ in range(int(poll_interval / 5)):
                            if self._stop_event.is_set():
                                break
                            await asyncio.sleep(5)

                    current_idx = (current_idx + 1) % len(subreddits)
                    continue

                # Reset consecutive empty counter when we get posts
                state.consecutive_empty = 0

                # Process posts
                new_posts_found = False
                for post in posts:
                    if self._stop_event.is_set():
                        break

                    # Check if already scraped (prevent duplicates)
                    if db.is_post_scraped(post.id, subreddit, sort_type):
                        logger.debug(f"Post {post.id} already scraped, skipping")
                        continue

                    # Send the post
                    try:
                        await self._send_post(channel, post, subreddit)

                        # Track in database
                        created_utc = (
                            post.created_utc
                            if hasattr(post, "created_utc")
                            else time.time()
                        )
                        db.add_scraped_post(
                            post.id,
                            subreddit,
                            sort_type,
                            title=post.title[:200] if hasattr(post, "title") else None,
                            created_utc=created_utc,
                        )

                        # Update state
                        state.total_sent += 1
                        if created_utc and (
                            state.last_post_timestamp is None
                            or created_utc > state.last_post_timestamp
                        ):
                            state.last_post_timestamp = created_utc

                        new_posts_found = True

                        # Update database session stats
                        db.update_session_stats(subreddit, sort_type, state.total_sent)

                        # Wait between posts
                        await asyncio.sleep(delay_seconds)

                    except Exception as e:
                        logger.error(f"Error sending post {post.id}: {e}")
                        continue

                # Move to next subreddit
                current_idx = (current_idx + 1) % len(subreddits)

                # Log progress periodically
                if current_idx == 0 and new_posts_found:
                    total_sent = sum(
                        s.total_sent for s in self.subreddit_states.values()
                    )
                    logger.info(
                        f"Completed round. Total posts sent this session: {total_sent}"
                    )

        except asyncio.CancelledError:
            logger.info("Continuous scraping cancelled")
            # Don't try to send messages during shutdown - session may be closed
            try:
                await channel.send("Continuous scraping stopped by user")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error in continuous scraping loop: {e}", exc_info=True)
            # Don't try to send messages during shutdown
            try:
                await channel.send(f"Error in continuous scraping: {str(e)[:200]}")
            except Exception:
                pass
        finally:
            self.is_running = False
            # Stop all sessions
            for key, state in self.subreddit_states.items():
                db.stop_session(state.subreddit, state.sort_type)
            logger.info("Continuous scraping loop ended")

    async def _fetch_time_based_posts(self, state: ScrapingState, batch_size: int):
        """Fetch posts for time-based sorts (new, hot, rising)

        For these sorts, we fetch the most recent posts and filter out ones we've already seen.
        """
        posts, error = await self.reddit_client.get_posts(
            state.subreddit, state.sort_type, batch_size * 2
        )

        if error:
            return None, error

        if not posts:
            return [], None

        # Filter posts: only return ones newer than our last seen post
        if state.last_post_timestamp:
            new_posts = [
                p
                for p in posts
                if hasattr(p, "created_utc")
                and p.created_utc > state.last_post_timestamp
            ]
            if new_posts:
                logger.info(
                    f"Found {len(new_posts)} new posts in r/{state.subreddit} (newer than {state.last_post_timestamp})"
                )
                return new_posts, None
            else:
                # All posts are old, return empty to trigger polling wait
                return [], None

        # First run - return all posts (they'll be filtered by database check later)
        return posts, None

    async def _fetch_static_posts(self, state: ScrapingState, batch_size: int):
        """Fetch posts for static sorts (top, controversial)

        For these sorts, we need to paginate through the list.
        """
        # Fetch a larger batch and use offset-based pagination
        # Note: Reddit API typically limits to 25-100 posts per request
        fetch_size = min(batch_size * 3, 25)  # Don't fetch too many at once

        posts, error = await self.reddit_client.get_posts(
            state.subreddit, state.sort_type, fetch_size
        )

        if error:
            return None, error

        if not posts:
            return [], None

        # For static sorts, we need to simulate pagination
        # Since we can't easily paginate with the current API, we'll use the database
        # to track which posts we've seen and return only new ones

        # Filter out already scraped posts
        new_posts = []
        for post in posts:
            if not db.is_post_scraped(post.id, state.subreddit, state.sort_type):
                new_posts.append(post)
                if len(new_posts) >= batch_size:
                    break

        if new_posts:
            logger.info(
                f"Found {len(new_posts)} unscraped posts in r/{state.subreddit} (sort: {state.sort_type})"
            )

        return new_posts, None

    async def _send_post(self, channel: discord.TextChannel, post, subreddit: str):
        """Send a single post to Discord"""
        media_path = None
        try:
            # Download media if present
            if post.url and not post.is_self and "reddit.com" not in post.url:
                media_path = await download_media(post.url, post.id, post)

            # Create embed
            embed, media_file, post_url = await create_post_embed(post, media_path)

            # Send with file if we have media
            file_to_send = None
            if media_path and media_file:
                file_to_send = discord.File(media_file)

            await channel.send(embed=embed, file=file_to_send)

            # Clean up media file
            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                    logger.debug(f"Deleted media: {media_path}")
                except Exception as e:
                    logger.error(f"Failed to delete media: {e}")

        except Exception as e:
            logger.error(f"Error in _send_post: {e}")
            raise


# Global scraper manager instance
scraper_manager = ScraperManager()
