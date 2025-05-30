import yt_dlp
import os
import re
from typing import Tuple, Optional, Dict

TEMP_AUDIO_DIR = "temp_audio" # Should align with main.py or be passed as config

def parse_youtube_url(youtube_url: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Parses a YouTube URL to extract video ID, start time, and end time (if specified via t= or start=/end=).
    Currently, only supports &t= seconds or &t=MmSs format.
    A default duration of 30 seconds will be assumed if only a start time is provided.
    Returns (video_id, start_seconds, end_seconds)
    """
    video_id_match = re.search(r"(?:v=|/embed/|/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})", youtube_url)
    if not video_id_match:
        return None, None, None
    video_id = video_id_match.group(1)

    start_seconds = None
    end_seconds = None
    default_duration = 30 # Default segment duration in seconds

    # Regex for &t= or ?t=
    time_match = re.search(r"[?&]t=([^&\s#]+)", youtube_url)
    if time_match:
        time_str = time_match.group(1)
        if 'm' in time_str or 's' in time_str:
            minutes = 0
            seconds = 0
            min_match = re.search(r"(\d+)m", time_str)
            if min_match:
                minutes = int(min_match.group(1))
            sec_match = re.search(r"(\d+)s", time_str)
            if sec_match:
                seconds = int(sec_match.group(1))
            start_seconds = (minutes * 60) + seconds
        else:
            try:
                start_seconds = int(time_str)
            except ValueError:
                start_seconds = None # Invalid time format

    if start_seconds is not None:
        end_seconds = start_seconds + default_duration

    return video_id, start_seconds, end_seconds

def download_youtube_segment(video_id: str, start_seconds: Optional[int] = None, end_seconds: Optional[int] = None) -> Optional[Dict[str, any]]:
    """
    Downloads a specific segment of a YouTube video's audio.
    If start_seconds and end_seconds are None, downloads a default 30s portion from the beginning.
    Saves the audio to a temporary file and returns a dictionary with metadata including the file path.
    """
    if not os.path.exists(TEMP_AUDIO_DIR):
        os.makedirs(TEMP_AUDIO_DIR)

    # Define a unique base for the output file, extension will be added by yt-dlp
    # Cleaner approach: let yt-dlp name it, then retrieve actual name from info_dict
    # For now, we'll use a predictable pattern and find it.
    output_base = f"{video_id}_segment"
    output_template_with_ext = os.path.join(TEMP_AUDIO_DIR, f"{output_base}.%(ext)s")
    final_output_mp3 = os.path.join(TEMP_AUDIO_DIR, f"{output_base}.mp3") # Assuming mp3 output

    # Clean up previous segment file for the same video_id if it exists
    if os.path.exists(final_output_mp3):
        try:
            os.remove(final_output_mp3)
        except OSError as e:
            print(f"Could not remove existing segment file {final_output_mp3}: {e}")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template_with_ext,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'download_archive': os.path.join(TEMP_AUDIO_DIR, 'downloaded_archive.txt') # Avoid re-downloading issues
    }

    actual_start_seconds = start_seconds
    actual_end_seconds = end_seconds

    if actual_start_seconds is not None and actual_end_seconds is not None:
        ydl_opts['postprocessor_args'] = [
            '-ss', str(actual_start_seconds),
            '-to', str(actual_end_seconds),
        ]
    else: # Default to first 30s if no specific range
        actual_start_seconds = 0
        actual_end_seconds = 30
        ydl_opts['postprocessor_args'] = [
             '-ss', str(actual_start_seconds),
             '-to', str(actual_end_seconds)
        ]

    target_url = f"https://www.youtube.com/watch?v={video_id}"
    video_info_dict = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                video_info_dict = ydl.extract_info(target_url, download=True) # Download and get info
            except yt_dlp.utils.DownloadError as e:
                if "Private video" in str(e) or "Video unavailable" in str(e):
                     raise ValueError(f"Video is private or unavailable: {video_id}") from e
                elif "Unsupported URL" in str(e):
                     raise ValueError(f"Invalid or unsupported YouTube URL: {target_url}") from e
                elif "age restricted" in str(e).lower():
                     raise ValueError(f"Video is age-restricted: {target_url}") from e
                print(f"yt-dlp download error for {target_url}: {e}")
                raise # Re-raise other download errors to be caught by the generic Exception

        if not video_info_dict:
            print(f"Could not retrieve video information for {target_url}")
            return None

        # The actual downloaded file path might be slightly different if yt-dlp changed filename
        # We assume it's the one we defined with .mp3 extension.
        downloaded_file_path = final_output_mp3
        if not os.path.exists(downloaded_file_path):
             # Fallback: try to find it based on `video_info_dict` if possible
            if '_filename' in video_info_dict and os.path.exists(video_info_dict['_filename']):
                downloaded_file_path = video_info_dict['_filename']
            else:
                # Last resort: search for the file if the naming was unexpected
                found_files = [os.path.join(TEMP_AUDIO_DIR, f) for f in os.listdir(TEMP_AUDIO_DIR) if f.startswith(output_base) and f.endswith('.mp3')]
                if found_files:
                    downloaded_file_path = sorted(found_files, key=os.path.getmtime, reverse=True)[0]
                else:
                    print(f"Error: Output MP3 file {final_output_mp3} not found after download attempt.")
                    return None
        
        print(f"Audio segment downloaded/processed to: {downloaded_file_path}")

        title = video_info_dict.get('title', 'Unknown Title')
        artist = video_info_dict.get('artist') or video_info_dict.get('uploader') or 'Unknown Artist'
        thumbnail_url = video_info_dict.get('thumbnail')
        
        m_start, s_start = divmod(actual_start_seconds, 60)
        m_end, s_end = divmod(actual_end_seconds, 60)
        segment_display_time = f"{int(m_start):02d}:{int(s_start):02d} - {int(m_end):02d}:{int(s_end):02d}"

        return {
            "file_path": downloaded_file_path,
            "video_id": video_id,
            "title": title,
            "artist": artist,
            "thumbnail_url": thumbnail_url,
            "requested_start_s": actual_start_seconds,
            "requested_end_s": actual_end_seconds,
            "segment_display_time": segment_display_time,
            "original_url": target_url
        }

    except ValueError as ve: # Catch our specific ValueErrors raised above
        print(f"Value error during YouTube processing: {ve}")
        raise # Re-raise to be caught by the API endpoint handler
    except Exception as e:
        print(f"An unexpected error occurred during YouTube download for {target_url}: {e}")
        # Clean up potentially partially downloaded file if it exists
        if os.path.exists(final_output_mp3):
            try: os.remove(final_output_mp3)
            except OSError as oe: print(f"Could not remove partial file {final_output_mp3}: {oe}")
        raise HTTPException(status_code=500, detail=f"Failed to process YouTube link: {e}") from e

if __name__ == '__main__':
    # --- Test functions ---
    test_urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Rick Astley - Never Gonna Give You Up"),
        ("https://www.youtube.com/watch?v=ZyhrYis509A&t=70s", "Beethoven - Moonlight Sonata (3rd Movement)"),
        ("https://www.youtube.com/watch?v=3JZ_D3ELwOQ&t=1m35s", "Interstellar Main Theme"),
        ("https://youtu.be/hKBMLrHjS3G8?t=60", "Shortform video with timestamp"), # Corrected: removed invalid char
        # ("https://www.youtube.com/watch?v=nonexistentvideo", "Non-existent video"), # This will raise an error
        # ("https://www.example.com", "Not a youtube video") # This will fail parsing
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
            except HTTPException as he:
                print(f"  HTTPException during download: {he.detail}")
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
 