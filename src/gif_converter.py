import os
import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List
from config import (
    MAX_FILE_SIZE_BYTES,
    GIF_MAX_DURATION_SECONDS,
    GIF_WIDTH,
    GIF_FPS,
    VIDEO_TARGET_SIZE_MB
)

logger = logging.getLogger(__name__)

# Compression settings
MAX_FILE_SIZE_MB = MAX_FILE_SIZE_BYTES / (1024 * 1024)
TARGET_FILE_SIZE_MB = VIDEO_TARGET_SIZE_MB

# GIF conversion levels (from highest to lowest quality)
# Starts with configured settings, then degrades
GIF_COMPRESSION_LEVELS: List[Dict] = [
    {'width': GIF_WIDTH, 'fps': GIF_FPS, 'colors': 256, 'dither': 'floyd_steinberg'},
    {'width': GIF_WIDTH, 'fps': 20, 'colors': 128, 'dither': 'floyd_steinberg'},
    {'width': 480, 'fps': 15, 'colors': 128, 'dither': 'bayer'},
    {'width': 320, 'fps': 10, 'colors': 64, 'dither': 'bayer'},
]

def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrapping=1:nokey=1',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
        else:
            logger.error(f"ffprobe error: {result.stderr}")
            return 0.0
    except Exception as e:
        logger.error(f"Error getting video duration: {e}")
        return 0.0

def get_file_size_mb(file_path: str) -> float:
    """Get file size in MB"""
    if os.path.exists(file_path):
        return os.path.getsize(file_path) / (1024 * 1024)
    return 0.0

def should_convert_to_gif(video_path: str, max_duration_seconds: int = None) -> bool:
    """
    Check if video should be converted to GIF
    
    Returns True if:
    - Video duration is less than max_duration_seconds
    - File is a valid video
    """
    if max_duration_seconds is None:
        max_duration_seconds = GIF_MAX_DURATION_SECONDS
    
    if not os.path.exists(video_path):
        return False
    
    duration = get_video_duration(video_path)
    logger.info(f"Video duration: {duration:.2f}s (max for GIF: {max_duration_seconds}s)")
    
    return duration > 0 and duration < max_duration_seconds

async def convert_to_gif(video_path: str, post_id: str) -> Optional[str]:
    """
    Convert video to GIF with iterative quality reduction
    
    Args:
        video_path: Path to input video
        post_id: Post ID for output filename
        
    Returns:
        Path to GIF if successful, None if all compression levels fail
    """
    duration = get_video_duration(video_path)
    logger.info(f"Converting video to GIF (duration: {duration:.2f}s)")
    
    for level in GIF_COMPRESSION_LEVELS:
        try:
            gif_path = f"temp/{post_id}_l{level['width']}_{level['fps']}.gif"
            
            # Build filter chain
            if level['dither'] == 'floyd_steinberg':
                dither_cmd = "paletteuse=dither=floyd_steinberg"
            else:
                dither_cmd = "paletteuse=dither=bayer,bayer_scale=5"
            
            filter_complex = (
                f"fps={level['fps']},"
                f"scale={level['width']}:-1:flags=lanczos,"
                f"split[s0][s1];"
                f"[s0]palettegen=max_colors={level['colors']}[p];"
                f"[s1][p]{dither_cmd}"
            )
            
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vf', filter_complex,
                '-loop', '0',
                '-y',  # Overwrite output
                gif_path
            ]
            
            logger.info(f"Converting to GIF (Level {GIF_COMPRESSION_LEVELS.index(level) + 1}/4): "
                       f"{level['width']}p, {level['fps']}fps, {level['colors']} colors")
            
            # Run ffmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {stderr.decode()}")
                if os.path.exists(gif_path):
                    os.remove(gif_path)
                continue
            
            # Check file size
            file_size_mb = get_file_size_mb(gif_path)
            logger.info(f"GIF created: {gif_path} ({file_size_mb:.2f}MB)")
            
            if file_size_mb <= MAX_FILE_SIZE_MB:
                logger.info(f"GIF conversion successful: {file_size_mb:.2f}MB")
                return gif_path
            else:
                logger.warning(f"GIF too large ({file_size_mb:.2f}MB > {MAX_FILE_SIZE_MB}MB), trying lower quality...")
                if os.path.exists(gif_path):
                    os.remove(gif_path)
                    
        except Exception as e:
            logger.error(f"Error in GIF conversion level: {e}")
            continue
    
    logger.error("All GIF compression levels exceeded size limit")
    return None

async def compress_video_two_pass(video_path: str, output_path: str, target_bitrate: float) -> bool:
    """
    Compress video using two-pass H.264 encoding
    
    Args:
        video_path: Input video path
        output_path: Output video path
        target_bitrate: Target bitrate in kbps
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Pass 1: Analyze video
        cmd_pass1 = [
            'ffmpeg',
            '-i', video_path,
            '-c:v', 'libx264',
            '-b:v', f'{target_bitrate}k',
            '-pass', '1',
            '-an',
            '-f', 'null',
            '-y',
            '/dev/null' if os.name != 'nt' else 'NUL'
        ]
        
        logger.info(f"Two-pass encoding pass 1 (bitrate: {target_bitrate}k)")
        process = await asyncio.create_subprocess_exec(
            *cmd_pass1,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Pass 2: Encode with analysis
        cmd_pass2 = [
            'ffmpeg',
            '-i', video_path,
            '-c:v', 'libx264',
            '-b:v', f'{target_bitrate}k',
            '-pass', '2',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y',
            output_path
        ]
        
        logger.info(f"Two-pass encoding pass 2")
        process = await asyncio.create_subprocess_exec(
            *cmd_pass2,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg two-pass error: {stderr.decode()}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error in two-pass encoding: {e}")
        return False

async def compress_video_crf(video_path: str, output_path: str, crf: int = 28, scale: Optional[str] = None) -> bool:
    """
    Compress video using CRF encoding
    
    Args:
        video_path: Input video path
        output_path: Output video path
        crf: CRF value (18-28, higher = more compression)
        scale: Scale filter (e.g., "480:-1")
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', 'medium',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-y',
            output_path
        ]
        
        if scale:
            cmd.insert(3, '-vf')
            cmd.insert(4, f'scale={scale}')
        
        logger.info(f"CRF encoding (CRF: {crf}, scale: {scale or 'original'})")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg CRF error: {stderr.decode()}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error in CRF encoding: {e}")
        return False

async def compress_video_if_needed(video_path: str, post_id: str, target_mb: float = TARGET_FILE_SIZE_MB) -> Optional[str]:
    """
    Compress video to fit under target size using multi-pass approach
    
    Args:
        video_path: Input video path
        post_id: Post ID for output filename
        target_mb: Target file size in MB
        
    Returns:
        Path to compressed video if successful, None if all compression fails
    """
    initial_size = get_file_size_mb(video_path)
    
    if initial_size <= MAX_FILE_SIZE_MB:
        logger.info(f"Video already under limit: {initial_size:.2f}MB")
        return video_path
    
    logger.info(f"Compressing video: {initial_size:.2f}MB -> target {target_mb:.2f}MB")
    
    # Get video duration for bitrate calculation
    duration = get_video_duration(video_path)
    if duration <= 0:
        logger.error("Cannot get video duration")
        return None
    
    # Calculate target bitrate for two-pass encoding
    # target_bitrate = (target_size_MB * 8192) / duration
    target_bitrate = (target_mb * 8192) / duration
    logger.info(f"Calculated target bitrate: {target_bitrate:.2f}kbps")
    
    compression_attempts = [
        ('two_pass', {'bitrate': target_bitrate}),
        ('crf', {'crf': 28}),
        ('crf_scaled', {'crf': 28, 'scale': '480:-1'}),
        ('crf_low', {'crf': 32}),
        ('crf_scaled_low', {'crf': 32, 'scale': '480:-1'}),
    ]
    
    for method, params in compression_attempts:
        try:
            output_path = f"temp/{post_id}_{method}.mp4"
            success = False
            
            if method == 'two_pass':
                success = await compress_video_two_pass(
                    video_path, output_path, params['bitrate']
                )
            elif method in ['crf', 'crf_scaled', 'crf_low', 'crf_scaled_low']:
                crf = params.get('crf', 28)
                scale = params.get('scale', None)
                success = await compress_video_crf(video_path, output_path, crf, scale)
            
            if success and os.path.exists(output_path):
                file_size_mb = get_file_size_mb(output_path)
                logger.info(f"Compression {method}: {file_size_mb:.2f}MB")
                
                if file_size_mb <= MAX_FILE_SIZE_MB:
                    logger.info(f"Compression successful: {file_size_mb:.2f}MB")
                    return output_path
                else:
                    logger.warning(f"Compression {method} still too large: {file_size_mb:.2f}MB")
                    if os.path.exists(output_path):
                        os.remove(output_path)
            else:
                if os.path.exists(output_path):
                    os.remove(output_path)
                    
        except Exception as e:
            logger.error(f"Error in compression {method}: {e}")
            continue
    
    logger.error("All video compression methods failed")
    return None
