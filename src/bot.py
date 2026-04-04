import discord
from discord import app_commands
import logging
import asyncio
import os
import random
from src.reddit_client import RedditClient
from src.media_downloader import download_media
from src.post_formatter import (
    create_post_embed,
    create_error_embed,
    create_progress_embed,
    create_completion_embed,
)
from src.utils import (
    validate_post_count,
    delete_file,
    setup_logging,
    ensure_temp_dir,
    clean_temp_files,
)
from src.scraper_manager import scraper_manager
from src.database import db
from config import (
    DISCORD_BOT_TOKEN,
    MAX_POSTS_PER_SCRAPE,
    POST_DELAY_SECONDS,
    validate_config,
)

logger = logging.getLogger(__name__)

intents = discord.Intents.default()


class RedditBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)


bot = RedditBot()

try:
    logger.info("Initializing Reddit client...")
    reddit_client = RedditClient()
    logger.info("Reddit client initialized successfully")
except Exception as e:
    reddit_client = None
    logger.error(f"Failed to initialize Reddit client: {e}", exc_info=True)
    print(f"[ERROR] Failed to initialize Reddit client: {e}")


@app_commands.choices(
    sort_type=[
        app_commands.Choice(name="Hot", value="hot"),
        app_commands.Choice(name="New", value="new"),
        app_commands.Choice(name="Rising", value="rising"),
        app_commands.Choice(name="Top", value="top"),
        app_commands.Choice(name="Controversial", value="controversial"),
    ]
)
@bot.tree.command(name="scrape", description="Scrape posts from a subreddit")
@app_commands.describe(
    subreddit="Subreddit name (without r/)",
    sort_type="Sort type for posts",
    count="Number of posts to scrape (1-25)",
)
async def scrape(
    interaction: discord.Interaction,
    subreddit: str,
    sort_type: app_commands.Choice[str],
    count: int = 5,
):
    logger.info(
        f"Received scrape command: subreddit={subreddit}, sort_type={sort_type.value}, count={count}"
    )

    if not reddit_client:
        await interaction.response.send_message(
            "❌ Reddit client not initialized. Check your credentials.", ephemeral=True
        )
        return

    subreddit = subreddit.lower().strip()
    if subreddit.startswith("r/"):
        subreddit = subreddit[2:]
    elif subreddit.startswith("/r/"):
        subreddit = subreddit[3:]

    is_valid, count = validate_post_count(count)
    if not is_valid:
        await interaction.response.send_message(
            f"❌ Invalid count! Must be between 1 and {MAX_POSTS_PER_SCRAPE}",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"🔍 Starting scrape: r/{subreddit} | Sort: {sort_type.name} | Count: {count}"
    )

    logger.info(f"Validating subreddit: {subreddit}")
    is_valid_sub, error_msg = await reddit_client.validate_subreddit(subreddit)
    if not is_valid_sub:
        logger.error(f"Subreddit validation failed for r/{subreddit}: {error_msg}")
        embed = await create_error_embed(subreddit, error_msg)
        await interaction.edit_original_response(embed=embed)
        return

    logger.info(f"Fetching {count} posts from r/{subreddit} (sort: {sort_type.value})")
    posts, error = await reddit_client.get_posts(subreddit, sort_type.value, count)

    if error:
        logger.error(f"Failed to fetch posts from r/{subreddit}: {error}")
        embed = await create_error_embed(subreddit, error)
        await interaction.edit_original_response(embed=embed)
        return

    if not posts:
        await interaction.edit_original_response(
            content=f"❌ No posts found in r/{subreddit}", embed=None
        )
        return

    success_count = 0
    skipped_count = 0
    progress_embed = await create_progress_embed(0, len(posts), subreddit)
    await interaction.edit_original_response(content="", embed=progress_embed)

    for idx, post in enumerate(posts, 1):
        media_path = None
        try:
            progress_embed = await create_progress_embed(idx, len(posts), subreddit)
            await interaction.edit_original_response(content="", embed=progress_embed)

            if post.is_self:
                logger.info(f"Post {idx}: Self/text post, sending without media")
            elif post.url:
                logger.info(f"Processing post {idx}/{len(posts)}: {post.url}")
                media_path = await download_media(post.url, post.id, post)

                if media_path is None:
                    logger.warning(
                        f"Post {idx}: Media download/conversion failed for {post.url}, skipping"
                    )
                    skipped_count += 1
                    continue

            embed, media_file, post_url = await create_post_embed(post, media_path)

            file_to_send = None
            if media_path and media_file:
                file_to_send = discord.File(media_file)

            await interaction.followup.send(embed=embed, file=file_to_send)
            success_count += 1
            logger.info(f"Post {idx} sent successfully")

            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                    logger.info(f"Media deleted immediately after send: {media_path}")
                except Exception as e:
                    logger.error(f"Failed to delete media {media_path}: {e}")

            if idx < len(posts):
                await asyncio.sleep(POST_DELAY_SECONDS)

        except Exception as e:
            logger.error(f"Error processing post {post.id}: {e}")
            await interaction.followup.send(f"⚠️ Error processing post: {str(e)[:100]}")
            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                    logger.info(f"Media deleted on error: {media_path}")
                except Exception as delete_error:
                    logger.error(f"Failed to delete media on error: {delete_error}")
            continue

    if skipped_count > 0:
        logger.info(f"Scrape complete: {success_count} posted, {skipped_count} skipped")

    completion_embed = await create_completion_embed(success_count, subreddit)
    await interaction.followup.send(embed=completion_embed)
    await interaction.edit_original_response(
        content=f"✅ Scrape complete! Posted {success_count} posts from r/{subreddit}",
        embed=None,
    )


@bot.tree.command(name="random", description="Get a random post from a subreddit")
@app_commands.describe(subreddit="Subreddit name (without r/)")
async def random_post(interaction: discord.Interaction, subreddit: str):
    if not reddit_client:
        await interaction.response.send_message(
            "❌ Reddit client not initialized.", ephemeral=True
        )
        return

    subreddit = subreddit.lower().strip().lstrip("r/").lstrip("/r/")
    await interaction.response.send_message(
        f"🎲 Getting random post from r/{subreddit}..."
    )

    try:
        posts, error = await reddit_client.get_posts(subreddit, "hot", 10)
        if error or not posts:
            await interaction.edit_original_response(
                content=f"❌ Could not fetch posts: {error}"
            )
            return

        post = random.choice(posts)
        media_path = None

        if post.url and not post.is_self and "reddit.com" not in post.url:
            media_path = await download_media(post.url, post.id, post)

        embed, media_file, _ = await create_post_embed(post, media_path)
        file_to_send = discord.File(media_file) if media_path and media_file else None
        await interaction.edit_original_response(content="", embed=embed)

        if file_to_send:
            await interaction.followup.send(file=file_to_send)

        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except:
                pass

    except Exception as e:
        logger.error(f"Error in random command: {e}")
        await interaction.edit_original_response(content=f"❌ Error: {str(e)[:100]}")


@bot.tree.command(name="subreddit", description="Get info about a subreddit")
@app_commands.describe(subreddit="Subreddit name (without r/)")
async def subreddit_info(interaction: discord.Interaction, subreddit: str):
    if not reddit_client:
        await interaction.response.send_message(
            "❌ Reddit client not initialized.", ephemeral=True
        )
        return

    subreddit = subreddit.lower().strip().lstrip("r/").lstrip("/r/")
    await interaction.response.send_message(f"🔍 Fetching info for r/{subreddit}...")

    try:
        is_valid, error = await reddit_client.validate_subreddit(subreddit)
        if not is_valid:
            await interaction.edit_original_response(
                content=f"❌ Subreddit not found: {error}"
            )
            return

        posts, _ = await reddit_client.get_posts(subreddit, "hot", 5)
        embed = discord.Embed(
            title=f"r/{subreddit}",
            description="✅ Subreddit exists and is accessible",
            color=0x00FF00,
        )

        if posts:
            embed.add_field(
                name="Recent Posts",
                value="\n".join(
                    [
                        f"• {p.title[:50]}..." if len(p.title) > 50 else f"• {p.title}"
                        for p in posts[:3]
                    ]
                ),
                inline=False,
            )

        await interaction.edit_original_response(content="", embed=embed)

    except Exception as e:
        logger.error(f"Error in subreddit info command: {e}")
        await interaction.edit_original_response(content=f"❌ Error: {str(e)[:100]}")


@bot.tree.command(name="search", description="Search for posts in a subreddit")
@app_commands.describe(subreddit="Subreddit name (without r/)", query="Search query")
async def search_posts(interaction: discord.Interaction, subreddit: str, query: str):
    if not reddit_client:
        await interaction.response.send_message(
            "❌ Reddit client not initialized.", ephemeral=True
        )
        return

    subreddit = subreddit.lower().strip().lstrip("r/").lstrip("/r/")
    query = query.strip()
    await interaction.response.send_message(
        f"🔍 Searching r/{subreddit} for: `{query}`..."
    )

    try:
        posts, error = await reddit_client.get_posts(subreddit, "new", 25)
        if error or not posts:
            await interaction.edit_original_response(
                content=f"❌ Could not fetch posts: {error}"
            )
            return

        matching_posts = [
            p
            for p in posts
            if query.lower() in p.title.lower()
            or (p.selftext and query.lower() in p.selftext.lower())
        ]

        if not matching_posts:
            await interaction.edit_original_response(
                content=f"❌ No posts found matching `{query}`"
            )
            return

        await interaction.edit_original_response(
            content=f"Found {len(matching_posts)} matching posts. Sending results..."
        )

        for idx, post in enumerate(matching_posts[:5], 1):
            media_path = None
            if post.url and not post.is_self and "reddit.com" not in post.url:
                media_path = await download_media(post.url, post.id, post)

            embed, media_file, _ = await create_post_embed(post, media_path)
            file_to_send = (
                discord.File(media_file) if media_path and media_file else None
            )
            await interaction.followup.send(embed=embed, file=file_to_send)

            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                except:
                    pass
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Error in search command: {e}")
        await interaction.edit_original_response(content=f"❌ Error: {str(e)[:100]}")


@app_commands.choices(
    sort_type=[
        app_commands.Choice(name="Hot", value="hot"),
        app_commands.Choice(name="New", value="new"),
        app_commands.Choice(name="Rising", value="rising"),
        app_commands.Choice(name="Top", value="top"),
        app_commands.Choice(name="Controversial", value="controversial"),
    ]
)
@bot.tree.command(
    name="scrape-continuous-start",
    description="Start continuous scraping from subreddits (runs indefinitely until stopped!)",
)
@app_commands.describe(
    subreddits="Comma-separated list of subreddits (e.g., 'memes,funny,technology')",
    sort_type="Sort type for posts (Hot/New/Rising poll for new posts, Top/Controversial go through history)",
    batch_size="Number of posts to check per batch per subreddit (1-10, default: 5)",
    delay_seconds="Seconds between individual post sends (default: 2.0)",
    poll_interval="For Hot/New/Rising: seconds to wait when no new posts found (default: 30.0)",
)
async def scrape_continuous_start(
    interaction: discord.Interaction,
    subreddits: str,
    sort_type: app_commands.Choice[str],
    batch_size: int = 5,
    delay_seconds: float = 2.0,
    poll_interval: float = 30.0,
):
    """Start continuous scraping that runs indefinitely until manually stopped

    For Hot/New/Rising: Continuously polls for new posts (waits poll_interval seconds when no new posts)
    For Top/Controversial: Goes through posts linearly without stopping
    """
    if not reddit_client:
        await interaction.response.send_message(
            "❌ Reddit client not initialized.", ephemeral=True
        )
        return

    # Parse subreddits (comma or space separated)
    subreddit_list = [
        s.strip() for s in subreddits.replace(",", " ").split() if s.strip()
    ]

    if not subreddit_list:
        await interaction.response.send_message(
            "❌ Please specify at least one subreddit!", ephemeral=True
        )
        return

    if len(subreddit_list) > 10:
        await interaction.response.send_message(
            "❌ Maximum 10 subreddits allowed at once!", ephemeral=True
        )
        return

    # Validate batch size
    if batch_size < 1 or batch_size > 10:
        batch_size = 5

    # Validate poll interval (minimum 10 seconds to avoid rate limits)
    if poll_interval < 10:
        poll_interval = 10

    await interaction.response.send_message(
        f"[STARTING] Continuous scrape for {len(subreddit_list)} subreddit(s):\n"
        f"**Subreddits:** {', '.join(subreddit_list)}\n"
        f"**Sort:** {sort_type.name}\n"
        f"**Batch size:** {batch_size} posts per check\n"
        f"**Delay:** {delay_seconds}s between posts\n"
        f"**Poll interval:** {poll_interval}s (when no new posts)\n\n"
        f"**This will run continuously until you use /scrape-continuous-stop**\n"
        f"- Posts sent in round-robin order (A->B->C->A->B->C...)\n"
        f"- No duplicates across restarts (tracked in database)\n"
        f"- For Hot/New/Rising: polls for NEW posts continuously\n"
        f"- For Top/Controversial: scrapes through all history without stopping"
    )

    # Start the continuous scraper
    success, message = await scraper_manager.start_continuous_scrape(
        subreddit_list,
        sort_type.value,
        interaction.channel,
        batch_size,
        delay_seconds,
        poll_interval,
    )

    if not success:
        await interaction.followup.send(f"[ERROR] {message}")


@bot.tree.command(
    name="scrape-continuous-stop", description="Stop all continuous scraping tasks"
)
async def scrape_continuous_stop(interaction: discord.Interaction):
    """Stop all active continuous scraping"""
    success, message = await scraper_manager.stop_all_scraping()

    if success:
        await interaction.response.send_message(f"Stopped: {message}", ephemeral=True)
    else:
        await interaction.response.send_message(f"Warning: {message}", ephemeral=True)


@bot.tree.command(
    name="sync",
    description="Sync slash commands to this server (use if commands don't appear)",
)
async def sync_commands(interaction: discord.Interaction):
    """Manually sync commands to current guild for immediate availability"""
    await interaction.response.send_message(
        "[SYNC] Syncing commands to this server...", ephemeral=True
    )
    try:
        guild = interaction.guild
        if guild:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await interaction.edit_original_response(
                content=f"[SYNCED] Synced {len(synced)} commands to **{guild.name}**. They should appear immediately! Type `/` to see them."
            )
        else:
            synced = await bot.tree.sync()
            await interaction.edit_original_response(
                content=f"[SYNCED] Synced {len(synced)} commands globally. They may take up to 1 hour to appear due to Discord caching."
            )
    except Exception as e:
        await interaction.edit_original_response(
            content=f"[ERROR] Failed to sync commands: {str(e)}"
        )


async def sync_commands(interaction: discord.Interaction):
    """Manually sync commands to current guild for immediate availability"""
    await interaction.response.send_message(
        "[SYNC] Syncing commands to this server...", ephemeral=True
    )
    try:
        guild = interaction.guild
        if guild:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await interaction.edit_original_response(
                content=f"[SYNCED] Synced {len(synced)} commands to **{guild.name}**. They should appear immediately! Type `/` to see them."
            )
        else:
            synced = await bot.tree.sync()
            await interaction.edit_original_response(
                content=f"[SYNCED] Synced {len(synced)} commands globally. They may take up to 1 hour to appear due to Discord caching."
            )
    except Exception as e:
        await interaction.edit_original_response(
            content=f"[ERROR] Failed to sync commands: {str(e)}"
        )


@bot.tree.command(
    name="scrape-continuous-status", description="Check status of continuous scraping"
)
async def scrape_continuous_status(interaction: discord.Interaction):
    """Show status of all active continuous scraping sessions"""
    sessions = scraper_manager.get_status()

    if not sessions:
        await interaction.response.send_message(
            "No active continuous scraping sessions.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Continuous Scraping Status",
        color=0x00FF00 if scraper_manager.is_running else 0xFFA500,
    )

    embed.add_field(
        name="Status",
        value="Running" if scraper_manager.is_running else "Not Running",
        inline=False,
    )

    for session in sessions:
        subreddit = session["subreddit"]
        sort_type = session["sort_type"]
        started_at = session.get("started_at", "Unknown")
        total_scraped = session.get("total_sent_this_session", 0)
        stored_posts = session.get("total_tracked", 0)

        embed.add_field(
            name=f"r/{subreddit} ({sort_type})",
            value=f"Started: {started_at}\nPosts this session: {total_scraped}\nTotal tracked: {stored_posts}",
            inline=True,
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="scrape-continuous-clear",
    description="Clear tracking history for a subreddit (start fresh next time)",
)
@app_commands.describe(
    subreddit="Subreddit name (without r/)",
    sort_type="Optional: specific sort type to clear, or leave blank to clear all",
)
async def scrape_continuous_clear(
    interaction: discord.Interaction, subreddit: str, sort_type: str = None
):
    """Clear tracking for a subreddit to start fresh"""
    subreddit = subreddit.lower().strip().lstrip("r/").lstrip("/r/")

    # Validate sort_type if provided
    if sort_type and sort_type.lower() not in [
        "hot",
        "new",
        "rising",
        "top",
        "controversial",
    ]:
        await interaction.response.send_message(
            f"❌ Invalid sort type: {sort_type}. Use: hot, new, rising, top, or controversial",
            ephemeral=True,
        )
        return

    deleted = db.clear_subreddit_tracking(subreddit, sort_type)

    if sort_type:
        await interaction.response.send_message(
            f"🗑️ Cleared {deleted} tracked posts for r/{subreddit} ({sort_type})\n"
            f"Next continuous scrape will start from the beginning for this subreddit/sort.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f"🗑️ Cleared {deleted} tracked posts for r/{subreddit} (all sorts)\n"
            f"Next continuous scrape will start from the beginning for this subreddit.",
            ephemeral=True,
        )


@bot.tree.command(name="status", description="Check bot status")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot Status", color=0x00FF00)

    embed.add_field(
        name="Reddit Client",
        value="Connected" if reddit_client else "Not Connected",
        inline=True,
    )
    embed.add_field(name="Discord", value="Online", inline=True)
    embed.add_field(name="Bot User", value=str(bot.user), inline=False)

    embed.add_field(
        name="Settings",
        value=f"Max Posts: {MAX_POSTS_PER_SCRAPE}\nDelay: {POST_DELAY_SECONDS}s",
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="Show bot help")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Reddit-Discord Bot Help", color=0x00FF00)

    embed.add_field(
        name="/scrape",
        value="Scrape posts from a subreddit\n**Usage:** `/scrape <subreddit> <sort_type> <count>`\n**Example:** `/scrape memes Hot 10`",
        inline=False,
    )

    embed.add_field(
        name="/scrape-continuous-start",
        value="Start continuous scraping from multiple subreddits. Runs until stopped!\n**Usage:** `/scrape-continuous-start <subreddits> <sort_type> [batch_size] [delay]`\n**Example:** `/scrape-continuous-start memes,funny,technology Hot 5 2`\n*Note: Posts are tracked in database*",
        inline=False,
    )

    embed.add_field(
        name="/scrape-continuous-stop",
        value="Stop all continuous scraping tasks",
        inline=False,
    )

    embed.add_field(
        name="/scrape-continuous-status",
        value="Check status of continuous scraping sessions",
        inline=False,
    )

    embed.add_field(
        name="/scrape-continuous-clear",
        value="Clear tracking history for a subreddit (start fresh next time)\n**Usage:** `/scrape-continuous-clear <subreddit> [sort_type]`",
        inline=False,
    )

    embed.add_field(
        name="/sync",
        value="Sync commands to this server for immediate availability\n**Usage:** `/sync`",
        inline=False,
    )

    embed.add_field(
        name="/random",
        value="Get a random post from a subreddit\n**Usage:** `/random <subreddit>`\n**Example:** `/random memes`",
        inline=False,
    )

    embed.add_field(
        name="/subreddit",
        value="Get info about a subreddit\n**Usage:** `/subreddit <name>`\n**Example:** `/subreddit python`",
        inline=False,
    )

    embed.add_field(
        name="/search",
        value="Search for posts in a subreddit\n**Usage:** `/search <subreddit> <query>`\n**Example:** `/search funny cat`",
        inline=False,
    )

    embed.add_field(
        name="Sort Types",
        value="`Hot` - Hot posts (default)\n`New` - Newest posts\n`Rising` - Rising posts\n`Top` - Top posts\n`Controversial` - Controversial",
        inline=False,
    )

    embed.add_field(
        name="Count/Batch Size",
        value=f"Number of posts (1-{MAX_POSTS_PER_SCRAPE})\nDefault: 5",
        inline=False,
    )

    embed.add_field(
        name="Supported Platforms",
        value="YouTube, Imgur, Gfycat, Streamable, Vimeo, and more!",
        inline=False,
    )

    embed.add_field(name="/status", value="Check bot status", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    logger.info(f"{bot.user} has connected to Discord!")
    logger.info(f"[READY] {bot.user} is online and ready!")
    logger.info("Use /scrape <subreddit> <sort> <count> to start scraping")
    logger.info("Use /help for more commands")
    print(f"[READY] {bot.user} is online and ready!")
    print("Use /scrape <subreddit> <sort> <count> to start scraping")
    print("Use /help for more commands")

    ensure_temp_dir()
    clean_temp_files()

    if reddit_client:
        logger.info("Reddit client is ready for use")

    # Sync slash commands globally
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} global command(s)")
        print(f"[SYNCED] {len(synced)} slash command(s)")
        print(
            "Note: Commands may take up to 1 hour to appear in Discord due to caching."
        )
        print(
            "If commands don't appear, try re-inviting the bot with 'applications.commands' scope."
        )
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
        print(f"[ERROR] Failed to sync commands: {e}")


def run_bot():
    setup_logging()

    try:
        validate_config()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print("Please check your .env file against .env.example")
        return

    if not DISCORD_BOT_TOKEN:
        print("❌ DISCORD_BOT_TOKEN not found in .env file")
        return

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
