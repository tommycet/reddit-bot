import discord
import logging
from datetime import datetime
from src.utils import format_number, truncate_text, is_adult_content
from src.media_downloader import SUPPORTED_PLATFORMS

logger = logging.getLogger(__name__)

async def create_post_embed(post, media_path=None):
    adult_indicator = "🔞 " if is_adult_content(post) else ""
    
    title = f"{adult_indicator}{post.title}"
    
    description = ""
    if post.selftext:
        description = truncate_text(post.selftext, 2000)
    
    embed = discord.Embed(
        title=title,
        url=f"https://reddit.com{post.permalink}",
        description=description,
        color=get_subreddit_color(post.subreddit.display_name)
    )
    
    embed.set_author(
        name=f"u/{post.author.name if post.author else '[deleted]'}",
        url=f"https://reddit.com/u/{post.author.name if post.author else ''}"
    )
    
    score_str = f"⬆️ {format_number(post.score)}"
    comments_str = f"💬 {format_number(post.num_comments)}"
    
    embed.add_field(name="Score", value=score_str, inline=True)
    embed.add_field(name="Comments", value=comments_str, inline=True)
    
    subreddit_name = post.subreddit.display_name_prefixed
    embed.set_footer(
        text=f"{subreddit_name} • Posted {format_timestamp(post.created_utc)}"
    )
    
    embed.timestamp = datetime.utcfromtimestamp(post.created_utc)
    
    is_external_link = False
    if post.url and not post.url.startswith('https://www.reddit.com/gallery/'):
        from urllib.parse import urlparse
        domain = urlparse(post.url).netloc.lower().replace('www.', '')
        is_external_link = any(platform in domain for platform in SUPPORTED_PLATFORMS)
    
    if not media_path:
        if post.url and post.url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            embed.set_image(url=post.url)
        elif post.url and not is_external_link and not post.is_self:
            if not post.url.startswith('https://www.reddit.com/'):
                embed.add_field(name="Link", value=f"[View]({post.url})", inline=False)
    
    return embed, media_path, post.url

def get_subreddit_color(subreddit_name):
    colors = {
        'askreddit': 0xFF4500,
        'funny': 0xFF871F,
        'pics': 0x46D9B4,
        'gaming': 0x0079D3,
        'worldnews': 0x0079D3,
        'videos': 0xFF4500,
        'memes': 0xFF871F,
        'technology': 0x0079D3,
    }
    
    return colors.get(subreddit_name.lower(), 0xFF4500)

def format_timestamp(created_utc):
    now = datetime.utcnow().timestamp()
    diff = now - created_utc
    
    if diff < 60:
        return "just now"
    elif diff < 3600:
        minutes = int(diff / 60)
        return f"{minutes} min ago"
    elif diff < 86400:
        hours = int(diff / 3600)
        return f"{hours}h ago"
    elif diff < 604800:
        days = int(diff / 86400)
        return f"{days}d ago"
    elif diff < 2592000:
        weeks = int(diff / 604800)
        return f"{weeks}w ago"
    elif diff < 31536000:
        months = int(diff / 2592000)
        return f"{months}mo ago"
    else:
        years = int(diff / 31536000)
        return f"{years}y ago"

async def create_error_embed(subreddit, error_msg):
    embed = discord.Embed(
        title="❌ Error",
        description=f"Failed to fetch posts from r/{subreddit}\n\n**Error:** {error_msg}",
        color=0xFF0000
    )
    return embed

async def create_progress_embed(current, total, subreddit):
    embed = discord.Embed(
        title=f"📥 Scraping r/{subreddit}",
        description=f"Processing post {current}/{total}...",
        color=0x00FF00
    )
    return embed

async def create_completion_embed(count, subreddit):
    embed = discord.Embed(
        title="✅ Scraping Complete",
        description=f"Successfully posted {count} posts from r/{subreddit}",
        color=0x00FF00
    )
    return embed
