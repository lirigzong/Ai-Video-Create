from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import openai
import requests
import json
import base64
from io import BytesIO
from PIL import Image
import moviepy as mp
from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
import asyncio
import tempfile
import shutil

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# API Keys
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# OpenAI client
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Create directories for generated content
VIDEOS_DIR = Path("/app/backend/generated_videos")
IMAGES_DIR = Path("/app/backend/generated_images")
AUDIO_DIR = Path("/app/backend/generated_audio")

for dir_path in [VIDEOS_DIR, IMAGES_DIR, AUDIO_DIR]:
    dir_path.mkdir(exist_ok=True)

# Define Models
class VideoRequest(BaseModel):
    prompt: str
    duration: int = Field(default=60, ge=10, le=600)  # 10 seconds to 10 minutes
    segments: int = Field(default=3, ge=1, le=10)  # 1 to 10 segments

class ScriptSegment(BaseModel):
    segment_id: int
    content: str
    duration: float
    image_prompt: str

class VideoScript(BaseModel):
    segments: List[ScriptSegment]
    total_duration: float

class VideoGeneration(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    duration: int
    segments: int
    status: str = "processing"
    video_url: Optional[str] = None
    script: Optional[VideoScript] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class VideoGenerationCreate(BaseModel):
    prompt: str
    duration: int = 60
    segments: int = 3

class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Helper Functions
async def generate_script_with_deepseek(prompt: str, duration: int, segments: int) -> VideoScript:
    """Generate a video script using DeepSeek API"""
    try:
        segment_duration = duration / segments
        
        deepseek_prompt = f"""
        Create a video script for: "{prompt}"
        
        Requirements:
        - Total video duration: {duration} seconds
        - Divide into {segments} equal segments
        - Each segment should be approximately {segment_duration:.1f} seconds when spoken
        - For each segment, provide:
          1. Engaging narration text (concise but informative)
          2. A detailed image prompt for DALL-E 3 (photorealistic description)
        
        Format your response as JSON:
        {{
            "segments": [
                {{
                    "segment_id": 1,
                    "content": "Narration text for segment 1",
                    "image_prompt": "Detailed photorealistic image description for DALL-E 3"
                }},
                ...
            ]
        }}
        
        Make sure the narration is natural, engaging, and fits the timing. Image prompts should be detailed and photorealistic.
        """
        
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": deepseek_prompt}],
                "temperature": 0.7
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail=f"DeepSeek API error: {response.text}")
        
        result = response.json()
        script_content = result["choices"][0]["message"]["content"]
        
        # Parse JSON from the response
        try:
            script_json = json.loads(script_content)
        except json.JSONDecodeError:
            # If direct JSON parsing fails, try to extract JSON from markdown
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', script_content, re.DOTALL)
            if json_match:
                script_json = json.loads(json_match.group(1))
            else:
                raise HTTPException(status_code=500, detail="Failed to parse script JSON")
        
        # Convert to VideoScript model
        segments = []
        for i, seg in enumerate(script_json["segments"]):
            segments.append(ScriptSegment(
                segment_id=i + 1,
                content=seg["content"],
                duration=segment_duration,
                image_prompt=seg["image_prompt"]
            ))
        
        return VideoScript(segments=segments, total_duration=duration)
    
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Script generation failed: {str(e)}")

async def generate_image_with_dalle(prompt: str, segment_id: int, video_id: str) -> str:
    """Generate an image using DALL-E 3"""
    try:
        # Clean and improve the prompt for DALL-E 3
        clean_prompt = prompt.strip()
        if len(clean_prompt) > 1000:
            clean_prompt = clean_prompt[:1000]  # DALL-E 3 has prompt length limits
        
        # Add style guidance for better results
        enhanced_prompt = f"High quality, photorealistic: {clean_prompt}. Professional lighting, detailed, 16:9 aspect ratio suitable for video."
        
        response = openai_client.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt,
            size="1792x1024",  # 16:9 aspect ratio for videos
            quality="hd",
            response_format="b64_json"
        )
        
        # Save the image
        image_data = base64.b64decode(response.data[0].b64_json)
        image_path = IMAGES_DIR / f"{video_id}_segment_{segment_id}.jpg"
        
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        return str(image_path)
    
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        # If DALL-E fails, create a simple colored placeholder image
        return await create_placeholder_image(prompt, segment_id, video_id)

async def create_placeholder_image(prompt: str, segment_id: int, video_id: str) -> str:
    """Create a placeholder image when DALL-E fails"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a simple image with text
        img = Image.new('RGB', (1792, 1024), color=(73, 109, 137))
        d = ImageDraw.Draw(img)
        
        # Add text
        text = f"Segment {segment_id}\n{prompt[:100]}..."
        d.text((50, 500), text, fill=(255, 255, 255))
        
        image_path = IMAGES_DIR / f"{video_id}_segment_{segment_id}.jpg"
        img.save(image_path)
        
        return str(image_path)
    
    except Exception as e:
        logger.error(f"Error creating placeholder image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image generation completely failed: {str(e)}")

async def generate_audio_with_tts(text: str, segment_id: int, video_id: str) -> str:
    """Generate audio using OpenAI TTS"""
    try:
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice="nova",  # You can make this configurable
            input=text
        )
        
        audio_path = AUDIO_DIR / f"{video_id}_segment_{segment_id}.mp3"
        response.stream_to_file(audio_path)
        
        return str(audio_path)
    
    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        # If TTS fails due to quota issues, create a silent audio placeholder
        return await create_placeholder_audio(text, segment_id, video_id)

async def create_placeholder_audio(text: str, segment_id: int, video_id: str) -> str:
    """Create a placeholder silent audio when TTS fails"""
    try:
        import numpy as np
        from scipy.io.wavfile import write
        import subprocess
        
        # Calculate duration based on text length (rough estimate: 150 words per minute)
        words = len(text.split())
        duration = max(3, words / 2.5)  # minimum 3 seconds
        
        # Generate silent audio
        sample_rate = 44100
        samples = int(sample_rate * duration)
        silent_audio = np.zeros(samples, dtype=np.int16)
        
        # Save as WAV first
        wav_path = AUDIO_DIR / f"{video_id}_segment_{segment_id}.wav"
        write(wav_path, sample_rate, silent_audio)
        
        # Convert to MP3 using ffmpeg
        mp3_path = AUDIO_DIR / f"{video_id}_segment_{segment_id}.mp3"
        subprocess.run([
            'ffmpeg', '-i', str(wav_path), '-acodec', 'mp3', '-y', str(mp3_path)
        ], check=True, capture_output=True)
        
        # Remove WAV file
        wav_path.unlink()
        
        return str(mp3_path)
    
    except Exception as e:
        logger.error(f"Error creating placeholder audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audio generation completely failed: {str(e)}")

async def create_video_from_assets(video_id: str, script: VideoScript) -> str:
    """Combine images and audio into a video using MoviePy"""
    try:
        clips = []
        
        for segment in script.segments:
            image_path = IMAGES_DIR / f"{video_id}_segment_{segment.segment_id}.jpg"
            audio_path = AUDIO_DIR / f"{video_id}_segment_{segment.segment_id}.mp3"
            
            if not image_path.exists() or not audio_path.exists():
                raise HTTPException(status_code=500, detail=f"Missing assets for segment {segment.segment_id}")
            
            # Load audio to get actual duration
            audio_clip = AudioFileClip(str(audio_path))
            actual_duration = audio_clip.duration
            
            # Create image clip with audio duration
            image_clip = ImageClip(str(image_path), duration=actual_duration)
            image_clip = image_clip.set_audio(audio_clip)
            
            clips.append(image_clip)
        
        # Concatenate all clips
        final_video = concatenate_videoclips(clips, method="compose")
        
        # Export video
        video_path = VIDEOS_DIR / f"{video_id}.mp4"
        final_video.write_videofile(
            str(video_path),
            fps=24,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='/tmp/temp-audio.m4a',
            remove_temp=True,
            verbose=False,
            logger=None
        )
        
        # Clean up clips
        final_video.close()
        for clip in clips:
            clip.close()
        
        return str(video_path)
    
    except Exception as e:
        logger.error(f"Error creating video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video creation failed: {str(e)}")

async def process_video_generation(video_id: str, request: VideoRequest):
    """Background task to process video generation"""
    try:
        # Update status to script generation
        await db.video_generations.update_one(
            {"id": video_id},
            {"$set": {"status": "generating_script"}}
        )
        
        # Generate script
        script = await generate_script_with_deepseek(
            request.prompt, request.duration, request.segments
        )
        
        # Update with script
        await db.video_generations.update_one(
            {"id": video_id},
            {"$set": {"script": script.dict(), "status": "generating_assets"}}
        )
        
        # Generate images and audio for each segment in parallel
        image_tasks = []
        audio_tasks = []
        
        for segment in script.segments:
            image_task = generate_image_with_dalle(
                segment.image_prompt, segment.segment_id, video_id
            )
            audio_task = generate_audio_with_tts(
                segment.content, segment.segment_id, video_id
            )
            image_tasks.append(image_task)
            audio_tasks.append(audio_task)
        
        # Wait for all assets to be generated
        await asyncio.gather(*image_tasks, *audio_tasks)
        
        # Update status to video creation
        await db.video_generations.update_one(
            {"id": video_id},
            {"$set": {"status": "creating_video"}}
        )
        
        # Create final video
        video_path = await create_video_from_assets(video_id, script)
        video_url = f"/api/videos/{video_id}.mp4"
        
        # Update with completed video
        await db.video_generations.update_one(
            {"id": video_id},
            {"$set": {"status": "completed", "video_url": video_url}}
        )
        
    except Exception as e:
        logger.error(f"Error in video generation pipeline: {str(e)}")
        await db.video_generations.update_one(
            {"id": video_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )

# API Routes
@api_router.get("/")
async def root():
    return {"message": "AI Video Generator API"}

@api_router.post("/generate-video", response_model=VideoGeneration)
async def create_video_generation(request: VideoGenerationCreate, background_tasks: BackgroundTasks):
    """Start video generation process"""
    video_generation = VideoGeneration(
        prompt=request.prompt,
        duration=request.duration,
        segments=request.segments
    )
    
    # Save to database
    await db.video_generations.insert_one(video_generation.dict())
    
    # Start background processing
    video_request = VideoRequest(
        prompt=request.prompt,
        duration=request.duration,
        segments=request.segments
    )
    background_tasks.add_task(process_video_generation, video_generation.id, video_request)
    
    return video_generation

@api_router.get("/video-status/{video_id}")
async def get_video_status(video_id: str):
    """Get the status of a video generation"""
    video = await db.video_generations.find_one({"id": video_id})
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Remove MongoDB ObjectId to avoid serialization issues
    if "_id" in video:
        del video["_id"]
    
    return video

@api_router.get("/videos")
async def list_videos():
    """List all generated videos"""
    videos = await db.video_generations.find().sort("created_at", -1).to_list(100)
    
    # Remove MongoDB ObjectIds to avoid serialization issues
    for video in videos:
        if "_id" in video:
            del video["_id"]
    
    return [VideoGeneration(**video) for video in videos]

@api_router.get("/videos/{video_id}.mp4")
async def get_video_file(video_id: str):
    """Serve video file"""
    video_path = VIDEOS_DIR / f"{video_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"video_{video_id}.mp4"
    )

# Test endpoints for individual API integrations
@api_router.post("/test-deepseek")
async def test_deepseek(prompt: str = "Give me 3 daily beauty tips"):
    """Test DeepSeek API integration"""
    try:
        script = await generate_script_with_deepseek(prompt, 60, 3)
        return {"status": "success", "script": script.dict()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@api_router.post("/test-dalle")
async def test_dalle(prompt: str = "A beautiful sunset over mountains"):
    """Test DALL-E 3 API integration"""
    try:
        image_path = await generate_image_with_dalle(prompt, 1, "test")
        return {"status": "success", "image_path": image_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@api_router.post("/test-tts")
async def test_tts(text: str = "Hello, this is a test of the text to speech functionality."):
    """Test OpenAI TTS API integration"""
    try:
        audio_path = await generate_audio_with_tts(text, 1, "test")
        return {"status": "success", "audio_path": audio_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Legacy routes
@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
