import discord
from discord.ext import commands
import logging
import asyncio
from src.reddit_client import RedditClient
from src.media_downloader import download_media
from src.post_formatter import (
    create_post_embed,
    create_error_embed,
    create_progress_embed,
    create_completion_embed
)
from src.utils import (
    validate_sort_type,
    validate_post_count,
    delete_file,
    setup_logging,
    ensure_temp_dir,
    clean_temp_files
)
from config import (
    DISCORD_BOT_TOKEN,
    MAX_POSTS_PER_SCRAPE,
    POST_DELAY_SECONDS,
    validate_config
)

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

try:
    logger.info("Initializing Reddit client...")
    reddit_client = RedditClient()
    logger.info("Reddit client initialized successfully")
except Exception as e:
    reddit_client = None
    logger.error(f"Failed to initialize Reddit client: {e}", exc_info=True)
    print(f"❌ Failed to initialize Reddit client: {e}")

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'✅ {bot.user} is online and ready!')
    logger.info(f'📝 Use !scrape <subreddit> <sort> <count> to start scraping')
    logger.info(f'📝 Use !help for more commands')
    print(f'✅ {bot.user} is online and ready!')
    print(f'📝 Use !scrape <subreddit> <sort> <count> to start scraping')
    print(f'📝 Use !help for more commands')

    ensure_temp_dir()
    clean_temp_files()
    
if reddit_client:
    logger.info("Reddit client is ready for use")

@bot.command(name='scrape')
async def scrape(ctx, subreddit: str = None, sort_type: str = 'hot', count: int = 5):
    logger.info(f"Received scrape command: subreddit={subreddit}, sort_type={sort_type}, count={count}")
    
    if not reddit_client:
        logger.error("Reddit client not initialized. Check your credentials.")
        await ctx.send("❌ Reddit client not initialized. Check your credentials.")
        return
    
    if not subreddit:
        await ctx.send("❌ Please specify a subreddit!\nUsage: `!scrape <subreddit> <sort> <count>`")
        return
    
    subreddit = subreddit.lower().strip()
    
    if subreddit.startswith('r/'):
        subreddit = subreddit[2:]
    elif subreddit.startswith('/r/'):
        subreddit = subreddit[3:]
    
    if not validate_sort_type(sort_type):
        await ctx.send(f"❌ Invalid sort type! Valid options: new, rising, hot, top")
        return
    
    sort_type = sort_type.lower()
    
    is_valid, count = validate_post_count(count)
    if not is_valid:
        await ctx.send(f"❌ Invalid count! Must be between 1 and {MAX_POSTS_PER_SCRAPE}")
        return
    
    logger.info(f"Validating subreddit: {subreddit}")
    is_valid_sub, error_msg = await reddit_client.validate_subreddit(subreddit)
    if not is_valid_sub:
        logger.error(f"Subreddit validation failed for r/{subreddit}: {error_msg}")
        embed = await create_error_embed(subreddit, error_msg)
        await ctx.send(embed=embed)
        return

    await ctx.send(f"🔍 Starting scrape: r/{subreddit} | Sort: {sort_type} | Count: {count}")

    logger.info(f"Fetching {count} posts from r/{subreddit} (sort: {sort_type})")
    posts, error = await reddit_client.get_posts(subreddit, sort_type, count)

    if error:
        logger.error(f"Failed to fetch posts from r/{subreddit}: {error}")
        embed = await create_error_embed(subreddit, error)
        await ctx.send(embed=embed)
        return
    
    if not posts:
        await ctx.send(f"❌ No posts found in r/{subreddit}")
        return
    
    success_count = 0
    status_msg = await ctx.send(embed=await create_progress_embed(0, len(posts), subreddit))
    
    for idx, post in enumerate(posts, 1):
        try:
            await status_msg.edit(embed=await create_progress_embed(idx, len(posts), subreddit))
            
            # Indented this block to be inside the try
            media_path = None
            
            if post.url and not post.is_self:
                media_path = await download_media(post.url, post.id, post)
                
                embed, media_file, post_url = await create_post_embed(post, media_path)
                
                file_to_send = None
                try:
                    if media_path and media_file:
                        file_to_send = discord.File(media_file)
                    
                    await ctx.send(embed=embed, file=file_to_send)
                    success_count += 1
                    
                finally:
                    if media_path:
                        await delete_file(media_path)
            
            if idx < len(posts):
                await asyncio.sleep(POST_DELAY_SECONDS)
                
        except Exception as e:
            logger.error(f"Error processing post {post.id}: {e}")
            await ctx.send(f"⚠️ Error processing post: {str(e)[:100]}")
            continue
    
    await status_msg.delete()
    await ctx.send(embed=await create_completion_embed(success_count, subreddit))

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Reddit-Discord Bot Help",
        color=0x00FF00
    )
    
    embed.add_field(
        name="📝 !scrape",
        value="Scrape posts from a subreddit\n**Usage:** `!scrape <subreddit> <sort> <count>`\n"
              "**Example:** `!scrape memes hot 10`",
        inline=False
    )
    
    embed.add_field(
        name="📊 Sort Types",
        value="`new` - Newest posts\n`rising` - Rising posts\n`hot` - Hot posts (default)\n`top` - Top posts",
        inline=False
    )
    
    embed.add_field(
        name="🔢 Count",
        value=f"Number of posts (1-{MAX_POSTS_PER_SCRAPE})\nDefault: 5",
        inline=False
    )
    
    embed.add_field(
        name="📺 Supported Platforms",
        value="YouTube, Imgur, Gfycat, Streamable, Vimeo, and more!",
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ !status",
        value="Check bot status",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name='status')
async def status(ctx):
    embed = discord.Embed(
        title="📊 Bot Status",
        color=0x00FF00
    )
    
    embed.add_field(name="Reddit Client", value="✅ Connected" if reddit_client else "❌ Not Connected", inline=True)
    embed.add_field(name="Discord", value="✅ Online", inline=True)
    embed.add_field(name="Bot User", value=str(bot.user), inline=False)
    
    embed.add_field(
        name="Settings",
        value=f"Max Posts: {MAX_POSTS_PER_SCRAPE}\nDelay: {POST_DELAY_SECONDS}s",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument!\nUse `!help` for usage information.")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)[:100]}")

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

if __name__ == '__main__':
    run_bot()