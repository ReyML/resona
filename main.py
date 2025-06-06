from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Body
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
from services.audio_processor import process_audio_segment

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
    embedding: Optional[List[float]] = None

class AnalysisResponse(BaseModel):
    source_segment_info: SegmentInfo
    similar_segments: List[SegmentInfo]

# --- API Endpoints ---

@app.get("/")
async def read_root():
    return {"message": f"Welcome to the RESONA API. Visit /{STATIC_DIR}/index.html for the app."}

@app.post("/api/analyze-segment", response_model=AnalysisResponse)
async def analyze_youtube_segment_endpoint(request_data: SegmentAnalysisRequest = Body(...)):
    youtube_url = request_data.youtube_url
    print(f"API: Received YouTube URL via JSON: {youtube_url}")
    
    try:
        video_id, start_s, end_s = parse_youtube_url(youtube_url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL or could not parse Video ID.")

        print(f"API: Parsed ID: {video_id}, Start: {start_s}s, End: {end_s}s")
        
        download_info = download_youtube_segment(video_id, start_s, end_s)
        
        if not download_info or not download_info.get("file_path"):
            raise HTTPException(status_code=500, detail="Failed to download or process YouTube segment.")

        file_path_for_processing = download_info.get("file_path")
        print(f"API: Segment downloaded: {file_path_for_processing}")

        # Process audio to get embedding
        segment_embedding = None
        if file_path_for_processing:
            segment_embedding = process_audio_segment(file_path_for_processing)
            if segment_embedding:
                print(f"API: Embedding generated for {file_path_for_processing}. Dimension: {len(segment_embedding)}")
            else:
                print(f"API: Failed to generate embedding for {file_path_for_processing}.")

        source_segment = SegmentInfo(
            id=f"yt_{video_id}_{start_s if start_s is not None else 0}_{end_s if end_s is not None else 'end'}",
            title=download_info.get("title", "Unknown Title"),
            artist=download_info.get("artist", "Unknown Artist"),
            youtube_link=download_info.get("original_url", youtube_url),
            thumbnail_url=download_info.get("thumbnail_url"),
            segment_display_time=download_info.get("segment_display_time", "N/A"),
            matched_features=["YouTube Segment", f"Duration: {(end_s if end_s else 0) - (start_s if start_s else 0)}s"],
            embedding=segment_embedding
        )
        
        similar_segments_placeholder = [
            SegmentInfo(
                id="similar_abc_placeholder", 
                title="Placeholder Similar Song 1", 
                artist="Demo Artist", 
                youtube_link="https://www.youtube.com/watch?v=placeholder1",
                thumbnail_url="https://placehold.co/400x225/E81C4F/white?text=Similar+1&font=lora",
                segment_display_time="01:00 - 01:30", 
                matched_features=["Similar Tempo", "Vibey Horns"],
                similarity_score=0.92
            )
        ]

        try:
            # Ensure cleanup happens for the correct path
            if file_path_for_processing and os.path.exists(file_path_for_processing):
                os.remove(file_path_for_processing)
                print(f"API: Cleaned up temporary file: {file_path_for_processing}")
        except Exception as e_clean:
            print(f"API: Error cleaning up file {file_path_for_processing}: {e_clean}")

        return AnalysisResponse(source_segment_info=source_segment, similar_segments=similar_segments_placeholder)

    except ValueError as ve:
        print(f"API: ValueError during YouTube processing: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException as he:
        print(f"API: HTTPException caught: {he.detail}")
        raise
    except Exception as e:
        print(f"API: Unexpected error in analyze_youtube_segment: {e}")
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

    # Process uploaded audio to get embedding
    segment_embedding_upload = None
    if os.path.exists(file_path):
        segment_embedding_upload = process_audio_segment(file_path)
        if segment_embedding_upload:
            print(f"API: Embedding generated for uploaded file {audio_file.filename}. Dimension: {len(segment_embedding_upload)}")
        else:
            print(f"API: Failed to generate embedding for uploaded file {audio_file.filename}.")

    source_info_placeholder = SegmentInfo(
        id=f"upload_{audio_file.filename.split('.')[0]}_{int(os.path.getmtime(file_path))}", 
        title=audio_file.filename, 
        artist="Uploaded Audio", 
        youtube_link="#", 
        thumbnail_url="https://placehold.co/400x225/777/fff?text=Audio+File",
        segment_display_time="Full duration",
        matched_features=["Uploaded File", "Local Analysis"],
        embedding=segment_embedding_upload
    )
    similar_segments_placeholder = [] 
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"API: Cleaned up temporary uploaded file: {file_path}")
    except Exception as e_clean:
        print(f"API: Error cleaning up uploaded file {file_path}: {e_clean}")

    return AnalysisResponse(source_segment_info=source_info_placeholder, similar_segments=similar_segments_placeholder)

# --- Main Execution Guard ---
if __name__ == "__main__":
    print("Starting Uvicorn server...")
    print(f"Frontend expected at: http://localhost:8000/{STATIC_DIR}/index.html")
    print(f"API docs available at: http://localhost:8000/docs")
    # Pass the app as an import string "filename:app_instance_name" for reload to work correctly
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 