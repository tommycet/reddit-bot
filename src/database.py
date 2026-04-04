import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(DATA_DIR, "scraper.db")


class ScraperDatabase:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _init_db(self):
        """Initialize database with tables"""
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Table for tracking scraped posts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraped_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL,
                subreddit TEXT NOT NULL,
                sort_type TEXT NOT NULL,
                title TEXT,
                created_utc REAL,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(post_id, subreddit, sort_type)
            )
        """)

        # Table for tracking active continuous scrapes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit TEXT NOT NULL,
                sort_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run_at TIMESTAMP,
                total_scraped INTEGER DEFAULT 0,
                UNIQUE(subreddit, sort_type)
            )
        """)

        # Index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraped_posts_lookup 
            ON scraped_posts(subreddit, sort_type, created_utc)
        """)

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def is_post_scraped(self, post_id: str, subreddit: str, sort_type: str) -> bool:
        """Check if a post has already been scraped"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 1 FROM scraped_posts 
            WHERE post_id = ? AND subreddit = ? AND sort_type = ?
        """,
            (post_id, subreddit.lower(), sort_type.lower()),
        )

        result = cursor.fetchone()
        conn.close()
        return result is not None

    def add_scraped_post(
        self,
        post_id: str,
        subreddit: str,
        sort_type: str,
        title: str = None,
        created_utc: float = None,
    ):
        """Add a post to the scraped posts table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO scraped_posts 
                (post_id, subreddit, sort_type, title, created_utc)
                VALUES (?, ?, ?, ?, ?)
            """,
                (post_id, subreddit.lower(), sort_type.lower(), title, created_utc),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error adding post {post_id}: {e}")
        finally:
            conn.close()

    def get_last_scraped_post(self, subreddit: str, sort_type: str) -> Optional[Tuple]:
        """Get the most recently scraped post for a subreddit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT post_id, created_utc FROM scraped_posts
            WHERE subreddit = ? AND sort_type = ?
            ORDER BY created_utc DESC
            LIMIT 1
        """,
            (subreddit.lower(), sort_type.lower()),
        )

        result = cursor.fetchone()
        conn.close()
        return result

    def get_oldest_scraped_post(
        self, subreddit: str, sort_type: str
    ) -> Optional[Tuple]:
        """Get the oldest scraped post for a subreddit (for resuming backwards)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT post_id, created_utc FROM scraped_posts
            WHERE subreddit = ? AND sort_type = ?
            ORDER BY created_utc ASC
            LIMIT 1
        """,
            (subreddit.lower(), sort_type.lower()),
        )

        result = cursor.fetchone()
        conn.close()
        return result

    def start_session(self, subreddit: str, sort_type: str):
        """Mark a scraping session as active"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO active_sessions (subreddit, sort_type, is_active, started_at)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(subreddit, sort_type) DO UPDATE SET
                is_active = 1, started_at = CURRENT_TIMESTAMP, total_scraped = 0
            """,
                (subreddit.lower(), sort_type.lower()),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error starting session: {e}")
        finally:
            conn.close()

    def stop_session(self, subreddit: str, sort_type: str):
        """Mark a scraping session as inactive"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE active_sessions 
                SET is_active = 0
                WHERE subreddit = ? AND sort_type = ?
            """,
                (subreddit.lower(), sort_type.lower()),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error stopping session: {e}")
        finally:
            conn.close()

    def stop_all_sessions(self):
        """Stop all active sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("UPDATE active_sessions SET is_active = 0")
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error stopping all sessions: {e}")
        finally:
            conn.close()

    def get_active_sessions(self) -> List[Tuple]:
        """Get all currently active sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT subreddit, sort_type, started_at, total_scraped
            FROM active_sessions
            WHERE is_active = 1
        """)

        results = cursor.fetchall()
        conn.close()
        return results

    def update_session_stats(self, subreddit: str, sort_type: str, total_scraped: int):
        """Update session statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE active_sessions 
                SET total_scraped = ?, last_run_at = CURRENT_TIMESTAMP
                WHERE subreddit = ? AND sort_type = ?
            """,
                (total_scraped, subreddit.lower(), sort_type.lower()),
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error updating session stats: {e}")
        finally:
            conn.close()

    def get_scraped_count(self, subreddit: str, sort_type: str) -> int:
        """Get count of scraped posts for a subreddit"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) FROM scraped_posts
            WHERE subreddit = ? AND sort_type = ?
        """,
            (subreddit.lower(), sort_type.lower()),
        )

        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def clear_old_posts(self, days: int = 30):
        """Clear posts older than specified days to prevent database bloat"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                DELETE FROM scraped_posts 
                WHERE scraped_at < datetime('now', ?)
            """,
                (f"-{days} days",),
            )
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Cleared {deleted} old posts from database")
        except sqlite3.Error as e:
            logger.error(f"Database error clearing old posts: {e}")
        finally:
            conn.close()

    def clear_subreddit_tracking(self, subreddit: str, sort_type: str = None):
        """Clear tracking for a specific subreddit (useful for restarting from scratch)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if sort_type:
                cursor.execute(
                    """
                    DELETE FROM scraped_posts 
                    WHERE subreddit = ? AND sort_type = ?
                """,
                    (subreddit.lower(), sort_type.lower()),
                )
            else:
                cursor.execute(
                    """
                    DELETE FROM scraped_posts 
                    WHERE subreddit = ?
                """,
                    (subreddit.lower(),),
                )

            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Cleared {deleted} tracked posts for r/{subreddit}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Database error clearing tracking: {e}")
            return 0
        finally:
            conn.close()

    def get_subreddit_stats(self, subreddit: str, sort_type: str) -> dict:
        """Get detailed stats for a subreddit/sort combination"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get count
            cursor.execute(
                """
                SELECT COUNT(*) FROM scraped_posts
                WHERE subreddit = ? AND sort_type = ?
            """,
                (subreddit.lower(), sort_type.lower()),
            )
            total_count = cursor.fetchone()[0]

            # Get oldest and newest
            cursor.execute(
                """
                SELECT MIN(created_utc), MAX(created_utc) 
                FROM scraped_posts
                WHERE subreddit = ? AND sort_type = ?
            """,
                (subreddit.lower(), sort_type.lower()),
            )
            result = cursor.fetchone()
            oldest = result[0] if result else None
            newest = result[1] if result else None

            return {
                "total_scraped": total_count,
                "oldest_post_timestamp": oldest,
                "newest_post_timestamp": newest,
            }
        except sqlite3.Error as e:
            logger.error(f"Database error getting stats: {e}")
            return {
                "total_scraped": 0,
                "oldest_post_timestamp": None,
                "newest_post_timestamp": None,
            }
        finally:
            conn.close()


# Global database instance
db = ScraperDatabase()
