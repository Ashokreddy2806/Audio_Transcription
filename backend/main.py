import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Depends, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.database import engine, SessionLocal, get_db
from backend import models
from backend.transcriber import transcribe_audio
from backend.analyzer import (
    analyze_transcript, 
    GEMINI_API_KEY, 
    upload_audio_to_gemini, 
    process_audio_and_jd_with_gemini, 
    get_mime_type
)

# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Audio Transcription & Interview Analysis")

@app.on_event("startup")
def configure_db():
    import sqlite3
    conn = sqlite3.connect("jobs.db")
    cursor = conn.cursor()
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if cursor.fetchone():
            # Check if column exists
            cursor.execute("PRAGMA table_info(jobs)")
            columns = [col[1] for col in cursor.fetchall()]
            if "job_description" not in columns:
                print("Adding job_description column to jobs table...")
                cursor.execute("ALTER TABLE jobs ADD COLUMN job_description TEXT")
                conn.commit()
                print("Column added successfully.")
    except Exception as e:
        print(f"Error checking/migrating database column: {e}")
    finally:
        conn.close()

# CORS middleware to allow frontend access from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(os.path.dirname(BASE_DIR), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount frontend static files
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

def process_audio_job(job_id: str, file_path: str, db_session_factory):
    # We open a new DB session inside the background thread
    db = db_session_factory()
    try:
        # 1. Update job to PROCESSING
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            print(f"Job {job_id} not found in database.")
            return
        job.status = "PROCESSING"
        db.commit()

        # Check if we have GEMINI_API_KEY configured.
        # If so, use it to perform both transcription and analysis in one cloud call (fast & high accuracy).
        if GEMINI_API_KEY:
            print(f"GEMINI_API_KEY detected. Running cloud-based transcription & analysis for Job {job_id}...")
            mime_type = get_mime_type(file_path)
            file_uri, file_name_api = upload_audio_to_gemini(file_path, mime_type, GEMINI_API_KEY)
            
            transcript_text, analysis_text = process_audio_and_jd_with_gemini(
                file_uri, file_name_api, mime_type, job.job_description, GEMINI_API_KEY
            )
            
            job.transcript = transcript_text
            job.analysis = analysis_text
            job.status = "COMPLETED"
            db.commit()
            print(f"Job {job_id} completed successfully via Gemini API.")
        else:
            # Fallback to local Whisper + local Ollama/Gemini transcript analyzer
            print(f"Starting local Whisper transcription for Job {job_id}...")
            transcript_text = transcribe_audio(file_path, job.job_description)
            
            job.transcript = transcript_text
            db.commit()

            print(f"Starting analysis for Job {job_id}...")
            analysis_text = analyze_transcript(transcript_text, job.job_description)
            
            job.analysis = analysis_text
            job.status = "COMPLETED"
            db.commit()
            print(f"Job {job_id} completed successfully via local pipeline.")
        
    except Exception as e:
        print(f"Error processing Job {job_id}: {str(e)}")
        db.rollback()
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.error_message = str(e)
            db.commit()
    finally:
        # Clean up the local file to save space
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleaned up local file: {file_path}")
            except Exception as ex:
                print(f"Could not remove temporary file: {ex}")
        db.close()

@app.post("/api/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_description: str = Form(None),
    db: Session = Depends(get_db)
):
    # Validate file extension
    allowed_extensions = {'.mp3', '.wav', '.m4a', '.webm', '.ogg'}
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Supported types: {', '.join(allowed_extensions)}"
        )

    # Create job ID & record with optional job description
    job_id = str(uuid.uuid4())
    db_job = models.Job(
        id=job_id, 
        filename=file.filename, 
        status="PENDING", 
        job_description=job_description
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    # Save audio file
    temp_filename = f"{job_id}{ext}"
    temp_file_path = os.path.join(UPLOAD_DIR, temp_filename)
    
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run processing task in background
    background_tasks.add_task(
        process_audio_job, 
        job_id, 
        temp_file_path, 
        SessionLocal
    )

    return {"job_id": job_id, "filename": file.filename, "status": "PENDING"}

@app.get("/api/jobs")
def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).all()
    return [{
        "id": j.id,
        "filename": j.filename,
        "status": j.status,
        "created_at": j.created_at,
        "updated_at": j.updated_at
    } for j in jobs]

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "job_description": job.job_description,
        "transcript": job.transcript,
        "analysis": job.analysis,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"message": "Job deleted successfully"}

# Serve Frontend static files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def read_root():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Audio Transcription API is running. Frontend index.html not found."}
