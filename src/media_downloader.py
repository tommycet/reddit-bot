import os
import asyncio
import logging
import aiohttp
import yt_dlp
from pathlib import Path
from urllib.parse import urlparse
from src.utils import get_file_extension, ensure_temp_dir
from config import MAX_FILE_SIZE_BYTES

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    'youtube.com', 'youtu.be',
    'redgifs.com', 'gfycat.com',
    'streamable.com', 'vimeo.com',
    'imgur.com'
}

async def download_media(url, post_id, post=None):
    ensure_temp_dir()
    
    try:
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
        
        if 'reddit.com/gallery/' in url or 'reddit.com/comments/' in url:
            logger.info(f"Skipping Reddit gallery/comment link: {url}")
            return None
        
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower().replace('www.', '')
        
        is_external = any(platform in domain for platform in SUPPORTED_PLATFORMS)
        
        if is_external:
            filepath = await download_with_ytdlp(url, post_id)
        else:
            filepath = await download_direct(url, post_id)
        
        if filepath and os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            if file_size > MAX_FILE_SIZE_BYTES:
                logger.warning(f"File too large: {file_size} bytes")
                os.remove(filepath)
                return None
        
        return filepath
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return None

async def download_with_ytdlp(url, post_id):
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
    extension = get_file_extension(url)
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
