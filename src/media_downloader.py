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

        # Handle Reddit direct media URLs (i.redd.it for images, v.redd.it for videos)
        if 'i.redd.it' in url:
            logger.info(f"Downloading Reddit direct image: {url}")
            filepath = await download_direct(url, post_id)
            if filepath and os.path.exists(filepath):
                logger.info(f"Reddit direct image downloaded: {filepath}")
                return filepath
            logger.error(f"Failed to download Reddit direct image: {url}")
            return None
        
        # v.redd.it URLs need special handling
        if 'v.redd.it' in url:
            # DASH fallback URLs (e.g. .../DASH_720.mp4?source=fallback) can be downloaded directly
            if '/DASH_' in url or '.mp4' in url.split('?')[0]:
                logger.info(f"Downloading DASH fallback URL directly: {url}")
                filepath = await download_direct(url, post_id)
                if filepath and os.path.exists(filepath):
                    logger.info(f"DASH video downloaded: {filepath}")
                    return filepath
                logger.warning(f"Direct DASH download failed, trying yt-dlp...")
            
            # For short v.redd.it URLs, use the full Reddit post URL with yt-dlp
            # (short URLs get 403'd with yt-dlp's generic extractor)
            if post and hasattr(post, 'permalink') and post.permalink:
                reddit_url = f"https://www.reddit.com{post.permalink}"
                logger.info(f"Using full Reddit URL for yt-dlp: {reddit_url}")
                filepath = await download_with_ytdlp(reddit_url, post_id)
            else:
                logger.info(f"Trying yt-dlp with v.redd.it URL: {url}")
                filepath = await download_with_ytdlp(url, post_id)
            
            if filepath and os.path.exists(filepath):
                logger.info(f"v.redd.it video downloaded: {filepath}")
                return filepath
            logger.error(f"Failed to download v.redd.it video: {url}")
            return None

        # Skip Reddit gallery/comment links but allow direct media URLs
        if 'reddit.com/gallery/' in url or 'reddit.com/comments/' in url:
            logger.info(f"Skipping Reddit gallery/comment link: {url}")
            return None

        logger.info(f"URL domain check: {url} -> is_external will be checked")

        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower().replace('www.', '')

        is_external = any(platform in domain for platform in SUPPORTED_PLATFORMS)

        # Download media
        if is_external:
            filepath = await download_with_ytdlp(url, post_id)
        else:
            filepath = await download_direct(url, post_id)

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

    output_path = f"temp/{post_id}.mp4"

    ydl_opts = {
        'format': 'bestvideo[height<=1080][filesize<{0}]+bestaudio/best[height<=1080][filesize<{0}]/best[filesize<{0}]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'max_filesize': MAX_FILE_SIZE_BYTES,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }
    ydl_opts['format'] = ydl_opts['format'].format(MAX_FILE_SIZE_BYTES)

    def download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return output_path
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return None

    loop = asyncio.get_event_loop()
    filepath = await loop.run_in_executor(None, download)

    if filepath and os.path.exists(filepath):
        logger.info(f"Downloaded with yt-dlp: {filepath}")
        return filepath

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