"""
FastAPI routes - Main API endpoints for Horizon AI Assistant
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import asyncio
import base64
import io
from PIL import Image
import time

# REMOVED: from services.overlay_manager import OverlayManager - Overlays now handled by frontend
from services.context_manager import AIContextManager
from services.auth_manager import AuthManager
from services.transcription_service import TranscriptionService  # NEW: Voice transcription
from ai.connection_manager import AIConnectionManager
from ai.tag_websocket_manager import TagWebSocketManager
from api.context_search import AutoContextManager, SearchMethod
from models.context_data import ContextData
from models.shortcut import Shortcut
from capture.ocr_processor import OCRProcessor

api_router = APIRouter()

# Dependency injection for managers
# REMOVED: get_overlay_manager - Overlays now handled by frontend

def get_context_manager() -> AIContextManager:
    from main import horizon_app
    return horizon_app.context_manager

def get_auth_manager() -> AuthManager:
    from main import horizon_app
    return horizon_app.auth_manager

def get_ai_connection_manager() -> AIConnectionManager:
    from main import horizon_app
    return horizon_app.ai_connection_manager

def get_tag_websocket_manager() -> TagWebSocketManager:
    from main import horizon_app
    return horizon_app.tag_websocket_manager

def get_auto_context_manager() -> AutoContextManager:
    from main import horizon_app
    return horizon_app.auto_context_manager

def get_ocr_processor() -> OCRProcessor:
    """Dependency to get OCR processor instance"""
    from main import horizon_app
    return horizon_app.ocr_processor

def get_transcription_service() -> TranscriptionService:
    """Dependency to get transcription service instance"""
    from main import horizon_app
    return horizon_app.transcription_service

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0"
    }

# Context API endpoints
@api_router.post("/context/capture")
async def capture_context(
    capture_image: bool = True,
    context_manager: AIContextManager = Depends(get_context_manager)
) -> Dict[str, Any]:
    """Capture current screen context (without screenshot - frontend provides images)"""
    try:
        context_data = await context_manager.capture_current_context(capture_image=False)
        
        return {
            "success": True,
            "data": {
                "selected_text": context_data.selected_text,
                "ocr_text": context_data.ocr_text,
                "browser_url": context_data.browser_url,
                "timestamp": context_data.timestamp.isoformat(),
                "note": "Screenshot processing handled by frontend"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/context/process-screenshot")
async def process_screenshot(
    image_data: str,
    preprocess: bool = True,
    extract_blocks: bool = False,
    context_manager: AIContextManager = Depends(get_context_manager)
) -> Dict[str, Any]:
    """Process screenshot from frontend and extract OCR text"""
    try:
        # Decode base64 image data
        image_bytes = base64.b64decode(image_data)
        
        # Process the screenshot
        result = await context_manager.process_external_screenshot(
            image_bytes, 
            preprocess=preprocess
        )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/context/search")
async def search_context(
    ocr_text: str,
    method: str = "sentence_chunks",
    auto_context_manager: AutoContextManager = Depends(get_auto_context_manager)
) -> Dict[str, Any]:
    """Search for context based on OCR text"""
    try:
        # Convert string method to SearchMethod enum
        search_method = SearchMethod.SENTENCE_CHUNKS
        if method == "full_text":
            search_method = SearchMethod.FULL_TEXT
        elif method == "keywords":
            search_method = SearchMethod.KEYWORDS
        
        # Connect if not already connected
        if not auto_context_manager.context_search_api.is_connected:
            await auto_context_manager.connect(search_method)
        
        # Perform search
        await auto_context_manager.search_context(ocr_text)
        
        return {
            "success": True,
            "message": "Context search initiated",
            "data": {
                "search_method": method,
                "query": ocr_text[:100] + "..." if len(ocr_text) > 100 else ocr_text
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/context/notes")
async def get_context_notes(
    auto_context_manager: AutoContextManager = Depends(get_auto_context_manager)
) -> Dict[str, Any]:
    """Get current context notes"""
    try:
        notes_data = []
        for note in auto_context_manager.context_notes:
            notes_data.append({
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "tags": note.tags,
                "created_at": note.created_at.isoformat() if note.created_at else None,
                "updated_at": note.updated_at.isoformat() if note.updated_at else None
            })
        
        return {
            "success": True,
            "data": {
                "notes": notes_data,
                "total_count": len(notes_data),
                "is_loading": auto_context_manager.is_loading
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/context/meeting")
async def update_meeting_context(
    meeting_text: str,
    context_type: str = "meeting_audio",
    context_manager: AIContextManager = Depends(get_context_manager)
) -> Dict[str, Any]:
    """Update context with meeting audio transcription"""
    try:
        # Store meeting context for AI assistance
        # This could be enhanced to use a proper context database
        meeting_context = {
            "type": context_type,
            "content": meeting_text,
            "timestamp": asyncio.get_event_loop().time(),
            "source": "system_audio"
        }
        
        # For now, just return success - could be enhanced to store in database
        return {
            "success": True,
            "data": {
                "context_stored": True,
                "context_length": len(meeting_text),
                "context_type": context_type
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update meeting context: {str(e)}")

# AI Chat endpoints
@api_router.post("/ai/send-message")
async def send_ai_message(
    text: str,
    smarter_analysis: bool = False,
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager),
    context_manager: AIContextManager = Depends(get_context_manager)
) -> Dict[str, Any]:
    """Send message to AI with current context"""
    try:
        # Capture current context (without screenshot - frontend provides images)
        context_data = await context_manager.capture_current_context(capture_image=False)
        
        # Send to AI and wait for complete response
        ai_response = await ai_manager.send_message(
            text=text,
            ocr_text=context_data.ocr_text,
            selected_text=context_data.selected_text,
            browser_url=context_data.browser_url,
            image_data=None,  # Frontend will provide via separate call
            smarter_analysis_enabled=smarter_analysis
        )
        
        return {
            "success": True,
            "message": "AI message sent successfully",
            "data": {
                "content": ai_response,
                "is_complete": True
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/ai/status")
async def get_ai_status(
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager)
) -> Dict[str, Any]:
    """Get AI connection status"""
    status = ai_manager.get_connection_status()
    
    return {
        "success": True,
        "data": {
            "connected": status["connected"],
            "receiving": status["receiving"],
            "message_count": status["message_count"],
            "reconnection_attempts": status["reconnection_attempts"]
        }
    }


@api_router.get("/ai/messages")
async def get_ai_messages(
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager)
) -> Dict[str, Any]:
    """Get AI message history"""
    try:
        messages_data = []
        for msg in ai_manager.last_messages:
            messages_data.append({
                "id": msg.id,
                "message": msg.message,
                "is_user": msg.is_user,
                "timestamp": msg.timestamp.isoformat()
            })
        
        return {
            "success": True,
            "data": {
                "messages": messages_data,
                "current_stream": ai_manager.message_stream,
                "is_receiving": ai_manager.is_receiving
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/ai/clear-conversation")
async def clear_ai_conversation(
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager)
) -> Dict[str, Any]:
    """Clear AI conversation history"""
    try:
        ai_manager.clear_conversation()
        return {
            "success": True,
            "message": "Conversation cleared successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Tag management endpoints
@api_router.get("/tags")
async def get_all_tags(
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager)
) -> Dict[str, Any]:
    """Get all tags"""
    try:
        tags_data = []
        for tag in tag_manager.tags:
            tags_data.append({
                "id": tag.id,
                "name": tag.name,
                "color": tag.color
            })
        
        return {
            "success": True,
            "data": {
                "tags": tags_data,
                "count": len(tags_data),
                "is_loading": tag_manager.is_loading,
                "is_connected": tag_manager.is_connected
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/tags/search")
async def search_tags(
    query: str,
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager)
) -> Dict[str, Any]:
    """Search tags by name"""
    try:
        matching_tags = tag_manager.get_tags_containing(query)
        
        tags_data = []
        for tag in matching_tags:
            tags_data.append({
                "id": tag.id,
                "name": tag.name,
                "color": tag.color
            })
        
        return {
            "success": True,
            "data": {
                "tags": tags_data,
                "count": len(tags_data),
                "query": query
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/tags/{tag_id}")
async def get_tag(
    tag_id: str,
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager)
) -> Dict[str, Any]:
    """Get specific tag by ID"""
    try:
        tag = tag_manager.get_tag(tag_id)
        
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        
        return {
            "success": True,
            "data": {
                "id": tag.id,
                "name": tag.name,
                "color": tag.color
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/tags/refresh")
async def refresh_tags(
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager)
) -> Dict[str, Any]:
    """Refresh tags from server"""
    try:
        await tag_manager.refresh_tags()
        return {
            "success": True,
            "message": "Tags refreshed successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/tags/status")
async def get_tag_status(
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager)
) -> Dict[str, Any]:
    """Get tag manager status"""
    return {
        "success": True,
        "data": {
            "connected": tag_manager.is_connected,
            "loading": tag_manager.is_loading,
            "error": tag_manager.error,
            "tag_count": len(tag_manager.tags),
            "tenant_name": tag_manager.tenant_name,
            "reconnection_attempts": tag_manager.reconnection_attempts
        }
    }


# REMOVED: Overlay API endpoints - Overlays now handled by frontend
# The following endpoints were removed since overlays are frontend-only:
# - POST /overlay/ai-assist/toggle
# - POST /overlay/auto-context/toggle  
# - POST /overlay/quick-capture/toggle
# - GET /overlay/states
# Frontend manages overlays directly without backend coordination

# System status endpoint (updated to remove overlay manager references)
@api_router.get("/system/status")
async def get_system_status(
    auth_manager: AuthManager = Depends(get_auth_manager),
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager),
    tag_manager: TagWebSocketManager = Depends(get_tag_websocket_manager),
    auto_context_manager: AutoContextManager = Depends(get_auto_context_manager)
) -> Dict[str, Any]:
    """Get comprehensive system status"""
    return {
        "success": True,
        "data": {
            "authentication": {
                "authenticated": auth_manager.is_authenticated,
                "tenant_name": auth_manager.get_tenant_name()
            },
            "ai_connection": {
                "connected": ai_manager.is_connected,
                "receiving": ai_manager.is_receiving,
                "message_count": len(ai_manager.message_history)
            },
            "tag_manager": {
                "connected": tag_manager.is_connected,
                "tag_count": len(tag_manager.tags),
                "loading": tag_manager.is_loading
            },
            "context_search": {
                "connected": auto_context_manager.context_search_api.is_connected,
                "note_count": len(auto_context_manager.context_notes),
                "loading": auto_context_manager.is_loading
            },
            "overlays": {
                "status": "frontend_managed",
                "note": "Overlay management handled entirely by frontend for better UI responsiveness"
            },
            "hotkeys": {
                "status": "frontend_managed", 
                "note": "Hotkey management moved to frontend for platform-specific handling"
            }
        }
    }

# Screenshot processing methods - New methods for frontend screenshots
@api_router.post("/screenshot/process")
async def process_screenshot_endpoint(
    image_data: str,
    preprocess: bool = True,
    extract_blocks: bool = False,
    ocr_processor: OCRProcessor = Depends(get_ocr_processor)
) -> Dict[str, Any]:
    """Process screenshot sent from frontend"""
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        
        # Extract text using OCR processor
        ocr_result = await ocr_processor.extract_text(
            image_bytes,
            preprocess=preprocess,
            extract_blocks=extract_blocks
        )
        
        # Get image metadata
        image = Image.open(io.BytesIO(image_bytes))
        
        return {
            "success": True,
            "data": {
                "ocr_text": ocr_result.text,
                "confidence": ocr_result.confidence,
                "blocks": ocr_result.blocks if extract_blocks else None,
                "image_info": {
                    "width": image.width,
                    "height": image.height,
                    "format": image.format or "PNG",
                    "size_bytes": len(image_bytes)
                },
                "processing_time": ocr_result.processing_time if hasattr(ocr_result, 'processing_time') else None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screenshot processing failed: {str(e)}")

# Voice Transcription API endpoints - NEW
@api_router.post("/voice/transcribe")
async def transcribe_audio(
    audio_data: str,
    sample_rate: int = 16000,
    audio_format: str = "float32",
    transcription_service: TranscriptionService = Depends(get_transcription_service)
) -> Dict[str, Any]:
    """Transcribe base64 encoded audio data to text"""
    try:
        # Transcribe audio using Whisper
        result = await transcription_service.transcribe_base64_audio(
            audio_base64=audio_data,
            sample_rate=sample_rate,
            audio_format=audio_format
        )
        
        return {
            "success": result.success,
            "data": {
                "text": result.text,
                "confidence": result.confidence,
                "processing_duration": result.duration,
                "audio_duration": result.audio_duration,
                "error": result.error
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@api_router.post("/voice/transcribe-and-send")
async def transcribe_and_send_to_ai(
    audio_data: str,
    sample_rate: int = 16000,
    audio_format: str = "float32",
    audio_source: str = "microphone",
    smarter_analysis: bool = False,
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    ai_manager: AIConnectionManager = Depends(get_ai_connection_manager),
    context_manager: AIContextManager = Depends(get_context_manager)
) -> Dict[str, Any]:
    """Transcribe audio and automatically send to AI with context"""
    try:
        # Step 1: Transcribe audio
        transcription_result = await transcription_service.transcribe_base64_audio(
            audio_base64=audio_data,
            sample_rate=sample_rate,
            audio_format=audio_format
        )
        
        if not transcription_result.success or not transcription_result.text.strip():
            return {
                "success": False,
                "error": "Transcription failed or empty",
                "data": {
                    "transcription": transcription_result.text,
                    "transcription_error": transcription_result.error
                }
            }
        
        # Step 2: Prepare text with audio source context
        if audio_source == "system_audio":
            prefixed_text = f"[System Audio] {transcription_result.text}"
            use_smarter_analysis = True  # Always use smarter analysis for system audio
        else:
            prefixed_text = transcription_result.text
            use_smarter_analysis = smarter_analysis
        
        # Step 3: Capture current context
        context_data = await context_manager.capture_current_context(capture_image=False)
        
        # Step 4: Send to AI
        ai_response = await ai_manager.send_message(
            text=prefixed_text,
            ocr_text=context_data.ocr_text,
            selected_text=context_data.selected_text,
            browser_url=context_data.browser_url,
            image_data=None,  # Frontend provides images separately
            smarter_analysis_enabled=use_smarter_analysis
        )
        
        return {
            "success": True,
            "data": {
                "transcription": {
                    "text": transcription_result.text,
                    "confidence": transcription_result.confidence,
                    "processing_duration": transcription_result.duration,
                    "audio_duration": transcription_result.audio_duration
                },
                "ai_response": {
                    "content": ai_response,
                    "is_complete": True
                },
                "audio_source": audio_source,
                "smarter_analysis_used": use_smarter_analysis
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice-to-AI pipeline failed: {str(e)}")

@api_router.get("/voice/status")
async def get_voice_transcription_status(
    transcription_service: TranscriptionService = Depends(get_transcription_service)
) -> Dict[str, Any]:
    """Get voice transcription service status"""
    try:
        status = transcription_service.get_status()
        
        return {
            "success": True,
            "data": {
                "whisper_available": status["whisper_available"],
                "model_loaded": status["model_loaded"],
                "model_name": status["model_name"],
                "expected_sample_rate": status["expected_sample_rate"],
                "endpoints": {
                    "transcribe": "/api/v1/voice/transcribe",
                    "transcribe_and_send": "/api/v1/voice/transcribe-and-send",
                    "status": "/api/v1/voice/status"
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/voice/reload-model")
async def reload_whisper_model(
    model_name: Optional[str] = None,
    transcription_service: TranscriptionService = Depends(get_transcription_service)
) -> Dict[str, Any]:
    """Reload Whisper model (optionally with different model)"""
    try:
        success = await transcription_service.reload_model(model_name)
        
        return {
            "success": success,
            "data": {
                "model_reloaded": success,
                "model_name": transcription_service.model_name,
                "model_loaded": transcription_service.is_loaded
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model reload failed: {str(e)}")
