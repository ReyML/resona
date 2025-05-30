from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import shutil
from typing import List, Dict, Any, Optional
from pydantic import BaseModel # Ensure BaseModel is imported early

# Placeholder for actual service imports
# from services.youtube_service import process_youtube_link
# from services.audio_processor import process_audio_file, extract_segment_features
# from services.firebase_service import find_similar_segments_in_db, save_segment_to_db

# --- Service Imports ---
# Assuming services directory is at the same level as main.py
from services.youtube_service import parse_youtube_url, download_youtube_segment

# --- Application Setup ---
app = FastAPI(
    title="RESONA API",
    description="API for analyzing audio segments and finding similar ones.",
    version="0.1.0"
)

# --- CORS Configuration ---
# Allows requests from your frontend (and others if needed)
# For development, often permissive. For production, restrict to your frontend's domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins. Change for production!
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Static Files Mounting ---
# Serve the index.html and any other static assets (CSS, JS if separated)
# Ensure 'static' directory exists at the root of your project and index.html is inside it.
STATIC_DIR = "static"
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# This assumes index.html is in the 'static' directory.
# You will need to move your index.html into a 'static' folder in your project root.
app.mount(f"/{STATIC_DIR}", StaticFiles(directory=STATIC_DIR), name="static")

# --- Directory Setup ---
TEMP_AUDIO_DIR = "temp_audio"
if not os.path.exists(TEMP_AUDIO_DIR):
    os.makedirs(TEMP_AUDIO_DIR)

# --- Pydantic Models (Data Schemas) ---
# These will be moved to models/segment.py later.

class SegmentAnalysisRequest(BaseModel):
    youtube_url: str

class SegmentInfo(BaseModel):
    id: str
    title: str
    artist: str
    youtube_link: str
    thumbnail_url: Optional[str] = None
    segment_display_time: str # e.g., "01:10 - 01:40"
    matched_features: List[str] = []
    similarity_score: Optional[float] = None

class AnalysisResponse(BaseModel):
    source_segment_info: SegmentInfo
    similar_segments: List[SegmentInfo]

# --- API Endpoints ---

@app.get("/")
async def read_root():
    return {"message": f"Welcome to the RESONA API. Visit /{STATIC_DIR}/index.html for the app."}

@app.post("/api/analyze-segment", response_model=AnalysisResponse)
async def analyze_youtube_segment_endpoint(youtube_url: str = Form(...)):
    print(f"API: Received YouTube URL: {youtube_url}")
    
    try:
        video_id, start_s, end_s = parse_youtube_url(youtube_url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL or could not parse Video ID.")

        print(f"API: Parsed ID: {video_id}, Start: {start_s}s, End: {end_s}s")
        
        # Download the segment
        # download_youtube_segment can raise ValueError or HTTPException
        download_info = download_youtube_segment(video_id, start_s, end_s)
        
        if not download_info or not download_info.get("file_path"):
            # This case should ideally be covered by exceptions in download_youtube_segment
            raise HTTPException(status_code=500, detail="Failed to download or process YouTube segment.")

        print(f"API: Segment downloaded: {download_info.get('file_path')}")

        # Create SegmentInfo for the source/downloaded segment
        source_segment = SegmentInfo(
            id=f"yt_{video_id}_{start_s if start_s is not None else 0}_{end_s if end_s is not None else 'end'}", # Unique ID for the segment
            title=download_info.get("title", "Unknown Title"),
            artist=download_info.get("artist", "Unknown Artist"),
            youtube_link=download_info.get("original_url", youtube_url),
            thumbnail_url=download_info.get("thumbnail_url"),
            segment_display_time=download_info.get("segment_display_time", "N/A"),
            matched_features=["YouTube Segment", f"Duration: {(end_s if end_s else 0) - (start_s if start_s else 0)}s"] # Example features
            # similarity_score is not applicable for source segment
        )

        # --- Placeholder for audio feature extraction and similarity search --- 
        # 1. Call audio_processor.extract_segment_features(download_info["file_path"])
        #    This would return a feature vector (e.g., MFCCs, embeddings).
        #    features = extract_segment_features(download_info["file_path"])
        # 2. Call firebase_service.save_segment_to_db(source_segment, features) (optional, if storing all processed)
        # 3. Call firebase_service.find_similar_segments_in_db(features)
        #    This would return a list of similar SegmentInfo objects from your database.
        #    similar_segments_from_db = find_similar_segments_in_db(features)
        
        # For now, using placeholder similar segments:
        similar_segments_placeholder = [
            SegmentInfo(
                id="similar_abc_placeholder", 
                title="Placeholder Similar Song 1", 
                artist="Demo Artist", 
                youtube_link="https://www.youtube.com/watch?v=placeholder1",
                thumbnail_url="https://via.placeholder.com/400x225/333/fff?text=Similar+1",
                segment_display_time="01:00 - 01:30", 
                matched_features=["Similar Tempo", "Vibey Horns"],
                similarity_score=0.92
            )
        ]
        # --- End Placeholder ---

        # Clean up the downloaded audio file after processing (important!)
        # We might move this to a background task or a finally block if feature extraction is long
        try:
            if os.path.exists(download_info["file_path"]):
                os.remove(download_info["file_path"])
                print(f"API: Cleaned up temporary file: {download_info['file_path']}")
        except Exception as e_clean:
            print(f"API: Error cleaning up file {download_info.get('file_path')}: {e_clean}")
            # Not a critical error to stop the request, but log it.

        return AnalysisResponse(source_segment_info=source_segment, similar_segments=similar_segments_placeholder)

    except ValueError as ve:
        print(f"API: ValueError during YouTube processing: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException as he:
        print(f"API: HTTPException caught: {he.detail}")
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        print(f"API: Unexpected error in analyze_youtube_segment: {e}")
        # Generic error for unexpected issues
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.post("/api/analyze-audio", response_model=AnalysisResponse)
async def analyze_audio_file_endpoint(audio_file: UploadFile = File(...)):
    file_path = os.path.join(TEMP_AUDIO_DIR, audio_file.filename)
    print(f"API: Receiving audio file: {audio_file.filename}")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)
        print(f"API: Audio file saved to: {file_path}")
    except Exception as e:
        print(f"API: Error saving file: {e}")
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")
    finally:
        audio_file.file.close()

    # --- Placeholder for audio feature extraction and similarity search --- 
    # 1. features = audio_processor.extract_segment_features(file_path)
    # 2. similar_segments_from_db = firebase_service.find_similar_segments_in_db(features)
    source_info_placeholder = SegmentInfo(
        id=f"upload_{audio_file.filename.split('.')[0]}_{int(os.path.getmtime(file_path))}", 
        title=audio_file.filename, 
        artist="Uploaded Audio", 
        youtube_link="#", 
        thumbnail_url="https://via.placeholder.com/400x225/777/fff?text=Audio+File",
        segment_display_time="Full duration", # Ideally, get duration using librosa here
        matched_features=["Uploaded File", "Local Analysis"]
    )
    similar_segments_placeholder = [] 
    # --- End Placeholder ---
    
    # Clean up the uploaded audio file
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"API: Cleaned up temporary uploaded file: {file_path}")
    except Exception as e_clean:
        print(f"API: Error cleaning up uploaded file {file_path}: {e_clean}")

    return AnalysisResponse(source_segment_info=source_info_placeholder, similar_segments=similar_segments_placeholder)

# --- Main Execution Guard ---
if __name__ == "__main__":
    # Make sure 'static' directory exists and index.html is in it.
    # A common setup is to have your index.html in a 'static' folder.
    # If index.html is in the root, you might need to adjust StaticFiles or create a route for it.
    print("Starting Uvicorn server...")
    print(f"Frontend expected at: http://localhost:8000/{STATIC_DIR}/index.html")
    print(f"API docs available at: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) 