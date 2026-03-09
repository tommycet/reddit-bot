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

✅ **Dynamic Subreddit Scraping** - Scrape any subreddit on demand
✅ **Multiple Sort Types** - Supports new, rising, hot, and top posts
✅ **External Media Support** - Downloads and sends media from:
   - YouTube
   - Imgur
   - Gfycat
   - Streamable
   - Vimeo
   - Direct video/image URLs
✅ **Sequential Posting** - Posts are sent one by one with proper delays
✅ **Auto Cleanup** - All media files deleted immediately after sending
✅ **Discord Embeds** - Reddit-style post formatting
✅ **Progress Tracking** - Real-time status updates during scraping
✅ **Error Recovery** - Continues processing even if individual posts fail
✅ **Rate Limit Compliance** - Respects Reddit and Discord API limits

---

## Prerequisites

Before you begin, ensure you have:

- ✅ **Python 3.8 or higher** installed
- ✅ A **Discord account** (for creating the bot)
- ✅ A **Reddit account** (for API access)
- ✅ A **Discord server** where you have admin rights
- ✅ Basic command line knowledge

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

---

## Usage

### Start the Bot

```bash
python bot.py
```

You should see:
```
✅ BotName#1234 is online and ready!
📝 Use !scrape <subreddit> <sort> <count> to start scraping
```

### Basic Commands

#### Scrape Posts

```
!scrape <subreddit> <sort_type> <count>
```

**Parameters:**
- `subreddit` - Subreddit name (with or without "r/")
- `sort_type` - One of: `new`, `rising`, `hot`, `top`
- `count` - Number of posts (1-25)

**Examples:**

```bash
# Scrape 10 hot posts from r/memes
!scrape memes hot 10

# Scrape 5 new posts from r/technology
!scrape technology new 5

# Scrape 25 top posts from r/funny
!scrape funny top 25

# Scrape 15 rising posts from r/gaming
!scrape gaming rising 15

# Subreddit with r/ prefix also works
!scrape r/pics hot 10
```

### Other Commands

```
!help    - Show help message with all commands
!status  - Check bot status and connection
```

---

## Supported Platforms

The bot automatically detects and downloads media from these external platforms:

| Platform | Type | Notes |
|----------|------|-------|
| **YouTube** | Video | Downloads best quality ≤1080p |
| **Imgur** | Image/Video/Album | Supports galleries |
| **Gfycat** | Video/GIF | High quality downloads |
| **Streamable** | Video | Fast video downloads |
| **Vimeo** | Video | Professional video platform |
| **Direct URLs** | Image/Video | Any direct media link |

**Special Handling:**
- Reddit-hosted videos are extracted and sent
- Images are sent as embeds or attachments
- Large files are automatically skipped (>8MB)
- Failed downloads show error but continue processing

---

## File Structure

```
reddit-bot/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── bot.py               # Discord bot & command handlers
│   ├── reddit_client.py     # Reddit API wrapper (PRAW)
│   ├── media_downloader.py  # External media download logic
│   ├── post_formatter.py    # Discord embed formatting
│   └── utils.py             # Utility functions
├── temp/                    # Temporary media storage (auto-cleaned)
├── logs/                    # Bot logs directory
├── .env                     # Your credentials (not in git)
├── .env.example             # Template for .env
├── .gitignore               # Git ignore file
├── requirements.txt         # Python dependencies
├── config.py                # Bot configuration
├── bot.py                   # Main entry point
└── README.md                # This file
```

---

## Security Notes

### ✅ Credential Safety

- **Never commit `.env` file** to version control
- **Never share bot token or API keys** publicly
- The `.gitignore` file excludes `.env` and sensitive directories
- All credentials are loaded from environment variables

### ✅ Data Privacy

- **No data is stored permanently**
- Media files are stored in `temp/` directory temporarily
- Files are deleted immediately after sending to Discord
- Bot logs don't contain sensitive information

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
3. Try without "r/" prefix: `!scrape memes` instead of `!scrape r/memes`

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

---

## Commands Reference

### 📥 !scrape

Scrape posts from a subreddit and send to Discord.

**Syntax:**
```
!scrape <subreddit> <sort_type> <count>
```

**Parameters:**
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| subreddit | string | ✅ Yes | Any subreddit name (with or without "r/") |
| sort_type | string | ⭕ No | `new`, `rising`, `hot`, `top` (default: `hot`) |
| count | integer | ⭕ No | 1-25 (default: 5) |

**Examples:**
```
!scrape memes              # Scrapes 5 hot posts from r/memes
!scrape technology new     # Scrapes 5 new posts from r/technology
!scrape funny top 10       # Scrapes 10 top posts from r/funny
!scrape r/gaming hot 25    # Scrapes 25 hot posts from r/gaming
```

---

### ❓ !help

Display help information and available commands.

**Syntax:**
```
!help
```

---

### 📊 !status

Check bot status, connection, and settings.

**Syntax:**
```
!status
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
