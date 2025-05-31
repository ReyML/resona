import yt_dlp
import os
import re
from urllib.parse import urlparse, parse_qs
import logging
from typing import Tuple, Optional, Dict, Any

TEMP_AUDIO_DIR = "temp_audio" # Should align with main.py or be passed as config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_time_to_seconds(time_str: Optional[str]) -> Optional[int]:
    if not time_str:
        return None
    if isinstance(time_str, int):
        return time_str
    if time_str.isdigit():
        return int(time_str)
    
    match_s = re.match(r"(\d+)s$", time_str)
    if match_s:
        return int(match_s.group(1))
    
    match_ms = re.match(r"(\d+)m(\d+)s$", time_str)
    if match_ms:
        return int(match_ms.group(1)) * 60 + int(match_ms.group(2))
        
    match_hms = re.match(r"(\d+)h(\d+)m(\d+)s$", time_str)
    if match_hms:
        return int(match_hms.group(1)) * 3600 + int(match_hms.group(2)) * 60 + int(match_hms.group(3))
    
    logger.warning(f"Could not parse time string: {time_str}")
    return None

def parse_youtube_url(url_string: str) -> Tuple[str, int, int]:
    parsed_url = urlparse(url_string)
    query_params = parse_qs(parsed_url.query)

    video_id = None
    if "v" in query_params:
        video_id = query_params["v"][0]
    elif parsed_url.hostname == "youtu.be":
        video_id = parsed_url.path[1:]
    
    if not video_id:
        raise ValueError("Could not extract video ID from URL.")

    start_seconds_user = None
    if "t" in query_params:
        start_seconds_user = parse_time_to_seconds(query_params["t"][0])

    end_seconds_user = None
    if "end" in query_params: # Using 'end' as a custom parameter for end time
        end_seconds_user = parse_time_to_seconds(query_params["end"][0])

    MAX_DURATION = 20
    DEFAULT_DURATION = 20

    start_seconds = 0
    end_seconds = DEFAULT_DURATION

    if start_seconds_user is not None:
        start_seconds = start_seconds_user
        if end_seconds_user is not None:
            if end_seconds_user > start_seconds:
                duration = end_seconds_user - start_seconds
                if duration > MAX_DURATION:
                    end_seconds = start_seconds + MAX_DURATION
                else:
                    end_seconds = end_seconds_user
            else: # end time is invalid or not after start time
                end_seconds = start_seconds + DEFAULT_DURATION 
                # Cap if default duration makes it too long (shouldn't happen if MAX_DURATION=DEFAULT_DURATION)
                # This case is mostly for clarity if MAX_DURATION and DEFAULT_DURATION differ
                if (end_seconds - start_seconds) > MAX_DURATION:
                     end_seconds = start_seconds + MAX_DURATION
        else: # Only start time provided
            end_seconds = start_seconds + DEFAULT_DURATION
            if (end_seconds - start_seconds) > MAX_DURATION: # Should not exceed max if default is 20 and max is 20
                end_seconds = start_seconds + MAX_DURATION
    else: # No start time provided, use 0 to DEFAULT_DURATION
        start_seconds = 0
        end_seconds = DEFAULT_DURATION
        # end_seconds_user could still be present if user provides ?end=10s but no t=
        # This logic prioritizes 't' for segment start. If no 't', it's 0-20.
        # If user provides ?end=10s but no t=, it's still 0-20s not 0-10s with current logic.
        # This could be refined if we want `end` to work independently of `t` for 0-`end`.
        # For now, `end` is only considered if `t` is also present.

    # Ensure start_seconds is not negative
    if start_seconds < 0:
        start_seconds = 0
        end_seconds = DEFAULT_DURATION # Recalculate end if start was negative

    # Final check to ensure end_seconds is always greater than start_seconds after adjustments
    if end_seconds <= start_seconds:
        end_seconds = start_seconds + DEFAULT_DURATION # Fallback to default duration
        if (end_seconds - start_seconds) > MAX_DURATION: # Ensure it still respects MAX_DURATION
            end_seconds = start_seconds + MAX_DURATION

    return video_id, start_seconds, end_seconds

def download_youtube_segment(video_id: str, start_seconds: int, end_seconds: int, output_dir: str = TEMP_AUDIO_DIR) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    
    # Sanitize video_id to prevent directory traversal or command injection issues
    safe_video_id = re.sub(r'[^a-zA-Z0-9_\-]', '', video_id)
    # Further safeguard against excessively long names, though yt-dlp might truncate anyway
    safe_video_id = safe_video_id[:50] 

    output_template = os.path.join(output_dir, f"{safe_video_id}_segment.%(ext)s")

    segment_duration = end_seconds - start_seconds
    if segment_duration <= 0:
        logger.warning(f"Segment duration for {video_id} is {segment_duration}s (start: {start_seconds}, end: {end_seconds}). FFmpeg requires positive duration. Setting to 1s.")
        segment_duration = 1 # Prevent FFmpeg error with -t 0 or negative

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'postprocessor_args': [
            '-ss', str(start_seconds),
            '-t', str(segment_duration)
        ],
        'quiet': False, 
        'no_warnings': False,
        'noprogress': True,
        'noplaylist': True, # Ensures only single video is downloaded if URL accidentally points to a playlist
    }

    downloaded_file_path = None
    video_info: Dict[str, Any] = {}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Attempting to download segment for {video_id} from {start_seconds}s to {end_seconds}s (duration: {segment_duration}s)")
            info_dict = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            
            # Construct the expected filename. yt-dlp replaces the original extension with .mp3.
            # We need to find which file was actually created.
            # A simple way is to list files and find the one matching the video_id pattern if ydl.prepare_filename is tricky.
            
            # Try to get the filename from info_dict if possible, otherwise scan the directory
            # This assumes yt-dlp has finished writing the file.
            # The exact filename after postprocessing can be tricky.
            # We'll assume the base name is `safe_video_id}_segment` and extension is `mp3`.
            downloaded_file_path = os.path.join(output_dir, f"{safe_video_id}_segment.mp3")
            
            if not os.path.exists(downloaded_file_path):
                logger.warning(f"Expected file {downloaded_file_path} not found after download attempt. Trying to find it by scanning directory...")
                found_files = [f for f in os.listdir(output_dir) if safe_video_id in f and f.endswith(".mp3")]
                if found_files:
                    downloaded_file_path = os.path.join(output_dir, found_files[0])
                    logger.info(f"Found file by scanning: {downloaded_file_path}")
                else:
                    logger.error(f"Could not find the downloaded MP3 segment for {safe_video_id} in {output_dir}")
                    raise FileNotFoundError(f"Downloaded MP3 segment for {safe_video_id} not found.")

            video_info = {
                "file_path": downloaded_file_path,
                "title": info_dict.get('title', "Unknown Title"),
                "artist": info_dict.get('artist') or info_dict.get('uploader') or "Unknown Artist",
                "album": info_dict.get('album', "Unknown Album"),
                "thumbnail_url": info_dict.get('thumbnail'),
                "original_url": f"https://www.youtube.com/watch?v={video_id}",
                "duration_seconds": segment_duration, 
                "start_time_seconds": start_seconds,
                "end_time_seconds": end_seconds,
                "segment_display_time": f"{start_seconds//60:02d}:{start_seconds%60:02d} - {end_seconds//60:02d}:{end_seconds%60:02d}"
            }
            logger.info(f"Successfully processed segment: {video_info.get('title')}, saved to {video_info.get('file_path')}")

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp DownloadError for video ID {video_id}: {str(e)}")
        error_str = str(e).lower()
        if "video is unavailable" in error_str or \
           "private video" in error_str or \
           "премьера" in error_str or \
           "this video is private" in error_str or \
           "members-only content" in error_str:
            raise ValueError(f"The video (ID: {video_id}) is unavailable, private, a premiere, or members-only.") from e
        raise # Re-raise other download errors
    except FileNotFoundError as e:
        logger.error(f"File not found error during segment processing for {video_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred in download_youtube_segment for video ID {video_id}: {str(e)}")
        raise

    return video_info

if __name__ == '__main__':
    # --- Test functions ---
    test_urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Standard, 0-20s"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "Start at 30s, 30-50s"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s", "Start at 1m5s (65s), 65-85s"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&end=25s", "10s to 25s (15s duration)"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&end=15s", "10s to 15s (5s duration)"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&end=40s", "10s to 40s (expect 10-30s, capped at 20s duration)"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&end=10s", "Only end time 10s (expect 0-20s with current logic)"),
        ("https://youtu.be/dQw4w9WgXcQ?t=5s", "Short URL, start 5s, 5-25s"),
        ("https://www.youtube.com/watch?v=non_existent_video_id_123", "Non-existent video"), # Expected to fail
        # ("https://www.youtube.com/watch?v= रुपए ", "Video with unicode that might be problematic for filenames - ID: रुपए"), # Example with unicode in ID. `safe_video_id` handles this.
        ("https://www.youtube.com/watch?v=video_is_private", "Private video placeholder ID - needs actual private video to test")
    ]

    print("--- Testing URL Parsing and Downloading ---")
    for url, name in test_urls:
        print(f"\nProcessing: {name} ({url})")
        vid_id, start, end = parse_youtube_url(url)
        print(f"  Parsed -> ID: {vid_id}, Start: {start}s, End: {end}s")
        
        if vid_id:
            print(f"  Attempting download for: {name} ({vid_id})...")
            try:
                download_info = download_youtube_segment(vid_id, start, end)
                if download_info:
                    print(f"  Successfully processed: {download_info['title']}")
                    print(f"  File at: {download_info['file_path']}")
                    print(f"  Segment: {download_info['segment_display_time']}")
                    # Clean up test file (optional - good for testing)
                    try:
                        if os.path.exists(download_info['file_path']):
                           os.remove(download_info['file_path'])
                           print(f"  Cleaned up: {download_info['file_path']}")
                    except Exception as e_clean:
                       print(f"  Error cleaning up {download_info['file_path']}: {e_clean}")
                else:
                    print(f"  Failed to process {name} (no download info returned).")
            except ValueError as ve:
                print(f"  Skipping download due to parsing/video error: {ve}")
            except Exception as e_main_test:
                print(f"  Unhandled error during download test for {name}: {e_main_test}")
        else:
            print(f"  Skipping download for {name} due to invalid YouTube URL or ID.")
        print("---")

    # Clean up download archive file
    archive_file_path = os.path.join(TEMP_AUDIO_DIR, 'downloaded_archive.txt')
    if os.path.exists(archive_file_path):
        try:
            os.remove(archive_file_path)
            print(f"Cleaned up download archive: {archive_file_path}")
        except Exception as e:
            print(f"Error cleaning up archive file: {e}")

    print("\nTesting completed. Manually check temp_audio for any unexpected remaining files.")
 