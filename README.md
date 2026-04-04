# Reddit-Discord Bot 🤖

Automatically scrape Reddit posts and send them to Discord with full media support, including external platforms like YouTube, Imgur, and more.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Discord Bot Setup](#discord-bot-setup)
- [Reddit API Setup](#reddit-api-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Supported Platforms](#supported-platforms)
- [File Structure](#file-structure)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Commands Reference](#commands-reference)

---

## Overview

This bot allows you to scrape posts from any Reddit subreddit and automatically post them to a Discord channel. It supports all types of content including text, images, videos, and external media from platforms like YouTube, Imgur, and more. Media files are downloaded temporarily, sent to Discord, and then immediately deleted from the local system.

---

## Features

1. **Dynamic Subreddit Scraping** - Scrape any subreddit on demand
2. **Multiple Sort Types** - Supports new, rising, hot, and top posts
3. **Hybrid Fetching (RSS + PRAW)** - RSS feeds for unlimited rate, PRAW as fallback
4. **Auto Video Compression** - Videos automatically compressed to fit Discord's 8MB limit
5. **Auto GIF Conversion** - Videos under 60s converted to GIF (720p, 30fps)
6. **External Media Support** - Downloads and sends media from various platforms
7. **Sequential Posting** - Posts are sent one by one with proper delays
8. **Auto Cleanup** - All media files deleted immediately after sending
9. **Discord Embeds** - Reddit-style post formatting
10. **Progress Tracking** - Real-time status updates during scraping
11. **Error Recovery** - Continues processing even if individual posts fail
12. **Rate Limit Compliance** - RSS eliminates rate limits, PRAW fallback with exponential backoff

---

## Prerequisites

Before you begin, ensure you have:

- ✅ **Python 3.8 or higher** installed
- ✅ A **Discord account** (for creating the bot)
- ✅ A **Reddit account** (for API access)
- ✅ A **Discord server** where you have admin rights

---

## Installation

### Step 1: Clone or Download the Repository

```bash
cd reddit-bot
```

### Step 2: Create Virtual Environment (Recommended)

```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see Configuration section below).

---

## Discord Bot Setup

### Step 1: Create Discord Application

1. Go to **[Discord Developer Portal](https://discord.com/developers/applications)**
2. Click **"New Application"**
3. Enter a name for your bot (e.g., "Reddit Scraper Bot")
4. Click **"Create"**

### Step 2: Create Bot User

1. In your application, go to **"Bot"** in the left sidebar
2. Click **"Add Bot"**
3. Click **"Yes, do it!"** to confirm
4. **Copy the bot token** - Click **"Reset Token"** if needed, then copy the token
   - ⚠️ **Important:** Save this token securely! You won't be able to see it again.

### Step 3: Set Bot Permissions

In the Bot section, enable these **Privileged Gateway Intents**:
- ✅ **Message Content Intent**
- ✅ **Server Members Intent** (optional)
- ✅ **Presence Intent** (optional)

Click **"Save Changes"**.

### Step 4: Invite Bot to Your Server

1. Go to **"OAuth2"** → **"URL Generator"** in the left sidebar
2. Under **"Scopes"**, check:
   - ✅ `bot`
3. Under **"Bot Permissions"**, check:
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Attach Files`
   - ✅ `Read Message History`
   - ✅ `Add Reactions`
4. Copy the generated URL at the bottom
5. Open the URL in your browser
6. Select your Discord server and click **"Authorize"**

### Step 5: Get Channel ID

1. Enable Developer Mode in Discord:
   - Go to **User Settings** → **Advanced** → **Enable Developer Mode**
2. Right-click the channel where you want the bot to post
3. Click **"Copy ID"**
4. Save this channel ID for later

---

## Reddit API Setup

### Step 1: Create Reddit Application

1. Go to **[Reddit App Preferences](https://www.reddit.com/prefs/apps)**
2. Scroll down to **"Developed Applications"**
3. Click **"Create App"** or **"Create Another App"**
4. Fill in the form:
   - **Name:** `RedditDiscordBot` (or any name you prefer)
   - **App Type:** Select **"script"**
   - **Description:** (Optional) "Bot for Discord"
   - **About URL:** (Optional) Your GitHub repo
   - **Redirect URI:** `http://localhost:8080`
5. Click **"Create App"**

### Step 2: Get Your Credentials

After creating the app, you'll see:

- **client_id:** The string under the app name (e.g., `AbCdEfGhIjKlMnOp`)
- **client_secret:** The string labeled "secret" (e.g., `QwErTyUiOpAsDfGhJkLzXcVbNm`)

### Step 3: Create User Agent

The user agent should follow this format:
```
RedditDiscordBot/1.0 by YourRedditUsername
```

Replace `YourRedditUsername` with your actual Reddit username.

---

## Configuration

Edit your `.env` file with the credentials you obtained:

```env
# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Reddit API Configuration
REDDIT_CLIENT_ID=your_reddit_client_id_here
REDDIT_CLIENT_SECRET=your_reddit_client_secret_here
REDDIT_USER_AGENT=RedditDiscordBot/1.0 by YourRedditUsername

# Optional Configuration
MAX_POSTS_PER_SCRAPE=25
POST_DELAY_SECONDS=2
MAX_FILE_SIZE_MB=8
```

### Configuration Variables Explained

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | ✅ Yes | Bot token from Discord Developer Portal |
| `REDDIT_CLIENT_ID` | ✅ Yes | Client ID from Reddit app |
| `REDDIT_CLIENT_SECRET` | ✅ Yes | Client secret from Reddit app |
| `REDDIT_USER_AGENT` | ✅ Yes | Unique identifier for Reddit API |
| `MAX_POSTS_PER_SCRAPE` | ⭕ No | Max posts per command (default: 25) |
| `POST_DELAY_SECONDS` | ⭕ No | Delay between posts in seconds (default: 2) |
| `MAX_FILE_SIZE_MB` | ⭕ No | Max file size in MB (default: 8) |
| `GIF_ENABLED` | ⭕ No | Enable auto GIF conversion (default: true) |
| `GIF_MAX_DURATION_SECONDS` | ⭕ No | Max video duration for GIF conversion (default: 60) |
| `GIF_WIDTH` | ⭕ No | GIF width in pixels (default: 720) |
| `GIF_FPS` | ⭕ No | GIF frames per second (default: 30) |
| `VIDEO_TARGET_SIZE_MB` | ⭕ No | Target video size for compression (default: 7.5) |
| `PRAW_RETRY_ATTEMPTS` | ⭕ No | PRAW retry attempts on rate limit (default: 3) |
| `PRAW_BASE_DELAY_SECONDS` | ⭕ No | Base delay for exponential backoff (default: 5) |

---

## Usage

### Start the Bot

```bash
python bot.py
```

You should see:
```
✅ BotName#1234 is online and ready!
📝 Use /scrape <subreddit> <sort> <count> to start scraping
```

### Basic Commands

#### Scrape Posts

```
/scrape <subreddit> <sort_type> <count>
```

**Parameters:**
- `subreddit` - Subreddit name (without "r/")
- `sort_type` - One of: `Hot`, `New`, `Rising`, `Top`, `Controversial`
- `count` - Number of posts (1-25)

**Examples:**

```bash
# Scrape 10 hot posts from r/memes
/scrape memes Hot 10

# Scrape 5 new posts from r/technology
/scrape technology New 5

# Scrape 25 top posts from r/funny
/scrape funny Top 25

# Scrape 15 rising posts from r/gaming
/scrape gaming Rising 15

# Scrape controversial posts from r/pics
/scrape pics Controversial 10
```

### Other Commands

```
/help    - Show help message with all commands
/status  - Check bot status and connection
/random  - Get a random post from a subreddit
/subreddit - Get info about a subreddit
/search  - Search for posts in a subreddit
```

---

## Supported Platforms

The bot automatically detects and downloads media from these external platforms:

| Platform | Type | Notes |
|----------|------|-------|
| **YouTube** | Video | Downloads best quality ≤1080p, converts to GIF if <60s |
| **Imgur** | Image/Video/Album | Supports galleries |
| **Gfycat** | Video/GIF | High quality downloads |
| **Streamable** | Video | Fast video downloads |
| **Vimeo** | Video | Professional video platform |
| **DailyMotion** | Video | Converts to GIF if <60s |
| **Direct URLs** | Image/Video | Any direct media link |

**Special Handling:**
- ✅ **Auto Compression**: Videos >8MB are compressed using multi-pass H.264 encoding
- ✅ **GIF Conversion**: Videos under 60 seconds are automatically converted to GIF (720p, 30fps)
- ✅ **Rate Limit Free**: RSS feeds eliminate rate limits for public subreddits
- ✅ **Smart Fallback**: PRAW used only when RSS fails
- ✅ **Immediate Cleanup**: Media deleted immediately after sending to Discord
- ✅ **Multi-level Compression**: 4 quality levels to ensure files fit under 8MB
- Failed downloads show error but continue processing

---

## File Structure

```
reddit-bot/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── bot.py               # Discord bot & command handlers
│   ├── reddit_client.py     # Reddit API wrapper (PRAW)
│   ├── reddit_rss.py        # RSS-based Reddit fetching
│   ├── media_downloader.py  # External media download logic
│   ├── post_formatter.py    # Discord embed formatting
│   ├── gif_converter.py     # GIF conversion & video compression
│   ├── utils.py             # Utility functions
│   ├── database.py          # SQLite database for tracking scraped posts
│   └── scraper_manager.py   # Continuous scraping manager
├── temp/                    # Temporary media storage (auto-cleaned)
├── logs/                    # Bot logs directory
├── data/                    # Database storage (scraper.db)
├── .env                     # Your credentials (not in git)
├── .env.example             # Template for .env
├── .gitignore               # Git ignore file
├── requirements.txt         # Python dependencies
├── config.py                # Bot configuration
├── bot.py                   # Main entry point
└── README.md                # This file
```

---

## Advanced Features

### 🎬 Automatic Video Compression

Videos larger than 8MB are automatically compressed using a multi-pass approach:

1. **Pass 1: Two-Pass H.264 Encoding**
   - Calculates optimal bitrate for target file size
   - First pass analyzes video, second pass encodes
   - Minimal quality loss, significant size reduction

2. **Pass 2: CRF Compression**
   - Uses Constant Rate Factor (CRF 28) for balance
   - Preserves visual quality while reducing size
   - Good for videos where pass 1 isn't enough

3. **Pass 3: Resolution Scaling**
   - Scales video to 480p if still too large
   - Last resort before giving up
   - Ensures compatibility with Discord's limits

**Result:** Most videos compressed to 7-8MB with excellent quality.

### 🎬 Automatic GIF Conversion

Videos under 60 seconds are automatically converted to GIF with these settings:

- **Resolution:** 720px width (height auto-scaled)
- **Frame Rate:** 30 FPS (smooth playback)
- **Colors:** 256 color palette with Floyd-Steinberg dithering
- **Quality:** High-quality Lanczos scaling

**Compression Levels:**
1. **Level 1:** 720p, 30fps, 256 colors (best quality)
2. **Level 2:** 720p, 20fps, 128 colors (if L1 > 8MB)
3. **Level 3:** 480p, 15fps, 128 colors (if L2 > 8MB)
4. **Level 4:** 320p, 10fps, 64 colors (last resort)

If all levels fail to produce GIF ≤8MB, the original video is sent instead.

### 🚀 Hybrid Reddit Client (RSS + PRAW)

The bot uses a smart hybrid approach:

1. **Primary: RSS Feeds**
   - No rate limits
   - No authentication required
   - Works for all public subreddits
   - Faster response times

2. **Fallback: PRAW API**
   - Used when RSS fails
   - Supports private subreddits (with authentication)
   - Exponential backoff on rate limits
   - 3 retry attempts with increasing delays

**Caching:** Subreddit validation cached for 1 hour to reduce API calls.

### 🔄 Continuous Scraping (Never Stops Until You Say So!)

The bot now supports **continuous scraping** that runs **forever** until you manually stop it!

**Two Modes Based on Sort Type:**

#### 📈 Mode 1: Hot/New/Rising (Live Feed Mode)
Continuously monitors for **new posts** as they come in:
- Polls subreddit every `poll_interval` seconds (default: 30s)
- Sends new posts immediately when found
- Waits when no new posts (doesn't stop, just pauses polling)
- **Perfect for:** Live monitoring, news feeds, trending content

#### 📊 Mode 2: Top/Controversial (Archive Mode)
Goes through **all posts** in the list without stopping:
- Sends posts linearly from top to bottom
- When reaching the end, cycles back through
- Skips already-sent posts (tracked in database)
- **Perfect for:** Binge-reading, archiving, catching up on all-time posts

**How It Works:**

**Single Subreddit:**
```
1. Bot fetches batch of posts from r/memes
2. Checks database - sends only new posts
3. For Hot/New/Rising: waits 30s, then checks again
4. For Top/Controversial: moves to next batch
5. REPEATS FOREVER until you run /scrape-continuous-stop
```

**Multiple Subreddits (Round-Robin):**
```
/scrape-continuous-start memes,funny,technology Hot

Loop:
  → Check r/memes for new posts
  → Check r/funny for new posts  
  → Check r/technology for new posts
  → Wait poll_interval
  → REPEAT FOREVER
```

**Key Features:**
- ✅ **Never stops automatically** - runs until you use `/scrape-continuous-stop`
- ✅ **No duplicates** - tracks all sent posts in database
- ✅ **Resumes on restart** - picks up exactly where it left off
- ✅ **Smart polling** - respects rate limits with configurable intervals
- ✅ **Round-robin** - cycles through multiple subreddits fairly

**Database Management:**
- Database auto-created at `data/scraper.db`
- Stores: post ID, subreddit, sort type, timestamp
- Prevents duplicate sending even across bot restarts
- Delete the file anytime to reset tracking

**Example Scenarios:**

**Live News Monitoring:**
```
/scrape-continuous-start worldnews,news New
→ Monitors both subreddits 24/7
→ Sends new posts as they appear
→ Runs forever until stopped
```

**Best of All Time Archive:**
```
/scrape-continuous-start gaming,pcgaming Top
→ Goes through top posts of all time
→ Never stops, cycles when reaches end
→ Perfect for catching up on classic posts
```

---

## Security Notes

### ✅ Credential Safety

- **Never commit `.env` file** to version control
- **Never share bot token or API keys** publicly
- The `.gitignore` file excludes `.env` and sensitive directories
- All credentials are loaded from environment variables

### ✅ Data Privacy

- **Media files are temporary**: Stored in `temp/` directory and deleted immediately after sending
- **Post tracking**: The database (`data/scraper.db`) only stores post IDs to prevent duplicates (no personal data)
- **No credentials in logs**: Bot logs don't contain sensitive information
- **Database is local**: SQLite database is stored locally and never uploaded anywhere
- **Optional cleanup**: You can delete `data/scraper.db` anytime to reset tracking

### ✅ Rate Limiting

- **Reddit:** 60 requests per minute (handled by PRAW)
- **Discord:** Respects Discord's global rate limits
- 2-second delay between posts by default (configurable)

---

## Troubleshooting

### Common Issues

#### ❌ "Missing required environment variables"

**Solution:** Check your `.env` file:
1. Ensure `.env` exists (copy from `.env.example`)
2. All required variables are filled:
   - `DISCORD_BOT_TOKEN`
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`

#### ❌ "Subreddit not found"

**Solutions:**
1. Check subreddit name spelling
2. Subreddit might be private or quarantined
3. Try different spelling: `/scrape memes` (without the "r/" prefix)

#### ❌ "Access denied to subreddit"

**Solutions:**
1. Subreddit is private or banned
2. Try a different subreddit
3. Check if your Reddit account has access

#### ❌ "Rate limited by Reddit"

**Solution:**
1. Wait 1-2 minutes before trying again
2. Reduce post count in your next command
3. Increase `POST_DELAY_SECONDS` in `.env`

#### ❌ Bot doesn't respond to commands

**Solutions:**
1. Check if bot has **"Message Content Intent"** enabled (Discord Developer Portal)
2. Verify bot has permissions in the channel:
   - Send Messages
   - Embed Links
   - Attach Files
3. Check bot logs in `logs/bot.log`

#### ❌ "File too large" errors

**Solutions:**
1. Files >8MB are automatically skipped (Discord's limit)
2. For larger files, you need Discord Nitro:
   - Update `MAX_FILE_SIZE_MB=25` in `.env`
3. External videos are downloaded in best quality ≤8MB

#### ❌ Media not downloading

**Solutions:**
1. Check if platform is in supported list
2. Video might be age-restricted (some platforms)
3. Check logs for specific error: `logs/bot.log`

#### ❌ "yt-dlp" errors

**Solutions:**
1. Update yt-dlp: `pip install --upgrade yt-dlp`
2. Some videos may be region-locked
3. Check if the URL is accessible in your browser

#### ❌ "ffmpeg not found" or GIF conversion errors

**Solutions:**
1. Install ffmpeg:
   - **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use `choco install ffmpeg`
   - **macOS:** `brew install ffmpeg`
   - **Linux:** `sudo apt install ffmpeg` or `sudo yum install ffmpeg`
2. Restart the bot after installing ffmpeg
3. Check ffmpeg installation: `ffmpeg -version`

#### ❌ Video compression taking too long

**Solutions:**
1. Compression time depends on video length and quality
2. Larger videos take longer (can be 2-5x the video duration)
3. Bot will wait for full compression (no timeout)
4. Consider reducing `MAX_POSTS_PER_SCRAPE` for faster processing

#### ❌ GIF quality too low

**Solutions:**
1. Check GIF settings in `.env`:
   - Increase `GIF_WIDTH` (default: 720)
   - Increase `GIF_FPS` (default: 30)
2. Higher quality = larger file size
3. If still >8MB, bot will automatically reduce quality

---

## Commands Reference

All commands use Discord **Slash Commands** (type `/` in the chat to see available commands).

### 📥 /scrape

Scrape posts from a subreddit and send to Discord.

**Syntax:**
```
/scrape <subreddit> <sort_type> <count>
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddit | string | ✅ Yes | Any subreddit name (without "r/") |
| sort_type | choice | ⭕ No | `Hot`, `New`, `Rising`, `Top`, `Controversial` (default: `Hot`) |
| count | integer | ⭕ No | 1-25 (default: 5) |

**Examples:**
```
/scrape memes Hot              # Scrapes 5 hot posts from r/memes
/scrape technology New 10      # Scrapes 10 new posts from r/technology
/scrape funny Top 10           # Scrapes 10 top posts from r/funny
/scrape gaming Rising 15       # Scrapes 15 rising posts from r/gaming
```

---

### 🔄 /scrape-continuous-start

Start continuous scraping from multiple subreddits. **Runs indefinitely until you manually stop it!**

**Features:**
- **Runs Forever**: Continuously scrapes until you use `/scrape-continuous-stop`
- **Linear Order**: Goes through posts one by one in chronological order
- **Multi-Subreddit**: Scrapes from each subreddit in rotation (A→B→C→A→B→C...)
- **Database Tracking**: Tracks sent posts to prevent duplicates across restarts
- **Smart Behavior**:
  - **Hot/New/Rising**: Polls continuously for NEW posts, waits when none found
  - **Top/Controversial**: Goes through ALL posts linearly without stopping

**Syntax:**
```
/scrape-continuous-start <subreddits> <sort_type> [batch_size] [delay_seconds] [poll_interval]
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddits | string | ✅ Yes | Comma-separated list (max 10) |
| sort_type | choice | ⭕ No | `Hot`, `New`, `Rising`, `Top`, `Controversial` (default: `Hot`) |
| batch_size | integer | ⭕ No | 1-10 posts to check per fetch (default: 5) |
| delay_seconds | float | ⭕ No | Seconds between posts (default: 2.0) |
| poll_interval | float | ⭕ No | Seconds to wait when no new posts (default: 30.0, min: 10) |

**Examples:**
```
# Continuously poll for new posts from r/memes
/scrape-continuous-start memes Hot

# Monitor multiple subreddits for new posts
/scrape-continuous-start memes,funny,technology New

# Go through all top posts (doesn't stop!)
/scrape-continuous-start gaming Top

# With custom settings
/scrape-continuous-start gaming,pcgaming New 3 1.5 60
```

**How it works by Sort Type:**

**Hot/New/Rising (Time-based):**
1. Fetches latest posts from the subreddit
2. Sends any posts newer than the last one sent
3. If no new posts, waits `poll_interval` seconds (default: 30s)
4. Checks again... repeats FOREVER until stopped
5. On restart: automatically resumes from where it left off

**Top/Controversial (Static):**
1. Goes through posts linearly from top to bottom
2. Sends posts one by one, tracking in database
3. When reaching the end, continues from the beginning
4. Never stops - keeps cycling through (skipping already-sent posts)
5. On restart: continues from last position

**Round-Robin Multi-Subreddit:**
```
With subreddits: memes, funny, technology
Cycle: memes(1) → funny(1) → technology(1) → memes(2) → funny(2) → technology(2) → ...
```

---

### 🛑 /scrape-continuous-stop

Stop all active continuous scraping tasks immediately.

**Syntax:**
```
/scrape-continuous-stop
```

---

### 📊 /scrape-continuous-status

Check the status of all active continuous scraping sessions.

**Shows:**
- Whether scraping is currently running
- Which subreddits are being scraped
- When each session started
- Number of posts sent this session
- Total posts tracked in database per subreddit

**Syntax:**
```
/scrape-continuous-status
```

---

### 🗑️ /scrape-continuous-clear

Clear the tracking history for a subreddit. Use this if you want to start scraping from the beginning again (reset all progress).

**Syntax:**
```
/scrape-continuous-clear <subreddit> [sort_type]
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddit | string | ✅ Yes | Subreddit name |
| sort_type | string | ⭕ No | `Hot`, `New`, `Rising`, `Top`, `Controversial` (leave blank to clear all sorts) |

**Examples:**
```
# Clear all tracking for a subreddit
/scrape-continuous-clear memes

# Clear only Hot tracking for a subreddit
/scrape-continuous-clear memes Hot
```

**Note:** This deletes the tracking data from the database. The next time you start continuous scraping for this subreddit, it will start from the beginning as if never scraped before.

---

### 🎲 /random

Get a random post from a subreddit.

**Syntax:**
```
/random <subreddit>
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddit | string | ✅ Yes | Any subreddit name |

---

### 📋 /subreddit

Get info about a subreddit.

**Syntax:**
```
/subreddit <name>
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| name | string | ✅ Yes | Any subreddit name |

---

### 🔍 /search

Search for posts in a subreddit.

**Syntax:**
```
/search <subreddit> <query>
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddit | string | ✅ Yes | Any subreddit name |
| query | string | ✅ Yes | Search text |

---

### ❓ /help

Display help information and available commands.

**Syntax:**
```
/help
```

---

### 📊 /status

Check bot status, connection, and settings.

**Syntax:**
```
/status
```

**Shows:**
- Reddit API connection status
- Discord connection status
- Bot user information
- Current settings (max posts, delay)

---

## 📝 License

This project is for educational and personal use. Please respect Reddit's and Discord's Terms of Service.

---

## 🤝 Contributing

Feel free to submit issues and pull requests!

---

## ⚠️ Disclaimer

This bot is not affiliated with Reddit Inc. or Discord Inc. Use responsibly and in accordance with both platforms' API terms of service.

---

## 📧 Support

For issues and questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review bot logs in `logs/bot.log`
3. Ensure all credentials are correct
4. Check API status pages:
   - [Reddit Status](https://www.redditstatus.com/)
   - [Discord Status](https://discordstatus.com/)

---

**Happy Scraping! 🎉**
