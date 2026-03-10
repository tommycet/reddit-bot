import os
import asyncio
import logging
import aiohttp
import yt_dlp
from pathlib import Path
from urllib.parse import urlparse
from src.utils import get_file_extension, ensure_temp_dir
from src.gif_converter import (
    should_convert_to_gif,
    convert_to_gif,
    compress_video_if_needed,
    get_file_size_mb
)
from config import MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    'youtube.com', 'youtu.be',
    'redgifs.com', 'gfycat.com',
    'streamable.com', 'vimeo.com',
    'imgur.com', 'dailymotion.com'
}

MAX_FILE_SIZE_MB = MAX_FILE_SIZE_BYTES / (1024 * 1024)

async def download_media(url, post_id, post=None):
    ensure_temp_dir()

    try:
        # Handle Reddit gallery
        if post and hasattr(post, 'is_gallery') and post.is_gallery:
            logger.info(f"Processing Reddit gallery: {url}")
            gallery_data = post.gallery_data
            if not gallery_data:
                logger.warning(f"No gallery data found for {post_id}")
                return None

            media_metadata = getattr(post, 'media_metadata', {})
            if not media_metadata:
                logger.warning(f"No media metadata for gallery {post_id}")
                return None

            first_item = gallery_data['items'][0]
            media_id = first_item['media_id']

            if media_id in media_metadata:
                media_info = media_metadata[media_id]
                if 's' in media_info and 'u' in media_info['s']:
                    image_url = media_info['s']['u']
                    return await download_direct(image_url, post_id)

            logger.warning(f"Could not extract image from gallery {post_id}")
            return None

        logger.info(f"download_media called: url={url}, post_id={post_id}")

        # Handle Reddit direct media URLs (i.redd.it for images)
        if 'i.redd.it' in url:
            logger.info(f"Downloading Reddit direct image: {url}")
            filepath = await download_direct(url, post_id)
            if filepath and os.path.exists(filepath):
                logger.info(f"Reddit direct image downloaded: {filepath}")
                return filepath
            logger.error(f"Failed to download Reddit direct image: {url}")
            return None
        
        # === Download phase ===
        filepath = None
        
        if 'v.redd.it' in url:
            # DASH fallback URLs (e.g. .../DASH_720.mp4?source=fallback) can be downloaded directly
            if '/DASH_' in url or '.mp4' in url.split('?')[0]:
                logger.info(f"Downloading DASH fallback URL directly: {url}")
                filepath = await download_direct(url, post_id)
                if filepath and os.path.exists(filepath):
                    logger.info(f"DASH video downloaded: {filepath}")
            
            # If direct download failed or it's a short v.redd.it URL, try yt-dlp
            if not filepath or not os.path.exists(filepath):
                if post and hasattr(post, 'permalink') and post.permalink:
                    reddit_url = f"https://www.reddit.com{post.permalink}"
                    logger.info(f"Using full Reddit URL for yt-dlp: {reddit_url}")
                    filepath = await download_with_ytdlp(reddit_url, post_id)
                else:
                    logger.info(f"Trying yt-dlp with v.redd.it URL: {url}")
                    filepath = await download_with_ytdlp(url, post_id)

        elif 'reddit.com' in url and '/gallery/' in url:
            # Gallery URL that wasn't resolved to individual images by _fetch_original_url.
            # Try yt-dlp as a last resort — it can sometimes extract gallery images.
            logger.info(f"Trying yt-dlp for unresolved gallery URL: {url}")
            filepath = await download_with_ytdlp(url, post_id)

        elif 'reddit.com' in url and '/comments/' in url:
            # This might be a post with an external embed (YouTube, RedGifs, etc.)
            # where the .json API failed to return the original URL.
            # Try yt-dlp with the Reddit URL — it can extract embedded videos.
            logger.info(f"Trying yt-dlp for Reddit post URL (may have external embed): {url}")
            filepath = await download_with_ytdlp(url, post_id)

        else:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower().replace('www.', '')
            is_external = any(platform in domain for platform in SUPPORTED_PLATFORMS)

            logger.info(f"URL domain check: {url} -> is_external={is_external}")

            if is_external:
                filepath = await download_with_ytdlp(url, post_id)
            else:
                filepath = await download_direct(url, post_id)

        # === Post-processing phase ===
        if not filepath or not os.path.exists(filepath):
            logger.warning(f"Download failed for {url}")
            return None

        # Check initial file size
        file_size_mb = get_file_size_mb(filepath)
        logger.info(f"Downloaded: {filepath} ({file_size_mb:.2f}MB)")

        # Step 1: Compress video if needed (for videos > 8MB)
        if filepath.endswith('.mp4') and file_size_mb > MAX_FILE_SIZE_MB:
            logger.warning(f"Video too large ({file_size_mb:.2f}MB), compressing...")
            compressed_path = await compress_video_if_needed(filepath, post_id)

            if compressed_path and os.path.exists(compressed_path):
                # Delete original
                if filepath != compressed_path:
                    os.remove(filepath)
                filepath = compressed_path
                file_size_mb = get_file_size_mb(filepath)
                logger.info(f"Video compressed: {filepath} ({file_size_mb:.2f}MB)")
            else:
                logger.error(f"Compression failed for {filepath}, skipping post")
                if os.path.exists(filepath):
                    os.remove(filepath)
                return None

        # Step 2: Convert to GIF if video < 60s
        if filepath.endswith('.mp4'):
            if should_convert_to_gif(filepath):
                logger.info(f"Video < 60s, converting to GIF: {filepath}")
                gif_path = await convert_to_gif(filepath, post_id)

                if gif_path and os.path.exists(gif_path):
                    # Delete original video
                    os.remove(filepath)
                    filepath = gif_path
                    file_size_mb = get_file_size_mb(filepath)
                    logger.info(f"Converted to GIF: {filepath} ({file_size_mb:.2f}MB)")
                else:
                    logger.warning(f"GIF conversion failed, using original video: {filepath}")
            else:
                logger.info(f"Video >= 60s or not suitable for GIF, keeping as MP4")

        # Final size check
        final_size_mb = get_file_size_mb(filepath)
        if final_size_mb > MAX_FILE_SIZE_MB:
            logger.error(f"Final file still too large ({final_size_mb:.2f}MB), skipping post")
            if os.path.exists(filepath):
                os.remove(filepath)
            return None

        return filepath

    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def download_with_ytdlp(url, post_id):
    """Download media using yt-dlp"""
    extension = get_file_extension(url)
    if extension == '.jpg' or extension == '.jpeg' or extension == '.png':
        return await download_direct(url, post_id)

    output_template = f"temp/{post_id}.%(ext)s"
    output_path = f"temp/{post_id}.mp4"

    ydl_opts = {
        # Don't filter by filesize — most platforms don't report it in metadata,
        # causing zero format matches. Post-download size check handles this instead.
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 30,
        'retries': 3,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }

    def download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Get the actual downloaded filename (extension might differ)
                if info:
                    downloaded_file = ydl.prepare_filename(info)
                    # yt-dlp might merge to .mp4
                    if os.path.exists(output_path):
                        return output_path
                    # Check if the file exists with a different extension
                    if downloaded_file and os.path.exists(downloaded_file):
                        return downloaded_file
            return output_path
        except Exception as e:
            logger.error(f"yt-dlp error for {url}: {e}")
            return None

    loop = asyncio.get_event_loop()
    filepath = await loop.run_in_executor(None, download)

    if filepath and os.path.exists(filepath):
        logger.info(f"Downloaded with yt-dlp: {filepath}")
        return filepath

    # Check if the file was saved with a different name pattern
    import glob
    matches = glob.glob(f"temp/{post_id}.*")
    if matches:
        filepath = matches[0]
        logger.info(f"Found downloaded file: {filepath}")
        return filepath

    logger.warning(f"yt-dlp download produced no file for: {url}")
    return None

async def download_direct(url, post_id):
    """Download media directly via HTTP"""
    extension = get_file_extension(url)
    logger.info(f"download_direct: url={url}, extension={extension}")
    output_path = f"temp/{post_id}{extension}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} for {url}")
                    return None

                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > MAX_FILE_SIZE_BYTES:
                    logger.warning(f"File too large: {content_length} bytes")
                    return None

                with open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        if f.tell() > MAX_FILE_SIZE_BYTES:
                            logger.warning("File size exceeded during download")
                            f.close()
                            os.remove(output_path)
                            return None

                logger.info(f"Downloaded directly: {output_path}")
                return output_path
    except asyncio.TimeoutError:
        logger.error(f"Timeout downloading {url}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None
    except Exception as e:
        logger.error(f"Error downloading directly: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None

def get_platform_name(url):
    """Get platform name from URL"""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')

    if 'youtube.com' in domain or 'youtu.be' in domain:
        return 'YouTube'
    elif 'gfycat.com' in domain:
        return 'Gfycat'
    elif 'streamable.com' in domain:
        return 'Streamable'
    elif 'vimeo.com' in domain:
        return 'Vimeo'
    elif 'imgur.com' in domain:
        return 'Imgur'

    return domain