"""
Transcription Service for Horizon AI Assistant
Handles voice-to-text transcription using Whisper ASR
"""

import logging
import asyncio
import numpy as np
import base64
import io
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Whisper ASR imports
try:
    from transformers import pipeline as hf_pipeline
    import torch
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

@dataclass
class TranscriptionResult:
    """Result of voice transcription"""
    text: str
    confidence: float
    duration: float
    success: bool
    error: Optional[str] = None
    audio_duration: Optional[float] = None

class TranscriptionService:
    """Manages voice-to-text transcription using Whisper ASR"""
    
    def __init__(self, model_name: str = "openai/whisper-tiny"):
        self.logger = logging.getLogger(__name__)
        self.whisper_pipeline = None
        self.model_name = model_name
        self.is_loaded = False
        
        # Whisper expects 16kHz audio
        self.WHISPER_SAMPLE_RATE = 16000
        
        # Initialize if available
        if WHISPER_AVAILABLE:
            asyncio.create_task(self._initialize_whisper())
        else:
            self.logger.warning("Whisper dependencies not available. Install transformers and torch.")
    
    async def _initialize_whisper(self) -> bool:
        """Initialize Whisper ASR model asynchronously"""
        try:
            if self.whisper_pipeline is not None:
                return True
            
            self.logger.info(f"Loading Whisper model: {self.model_name}")
            
            # Load model in thread pool to avoid blocking
            self.whisper_pipeline = await asyncio.get_event_loop().run_in_executor(
                None, self._load_whisper_model
            )
            
            self.is_loaded = True
            self.logger.info("✓ Whisper ASR model loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load Whisper model: {e}")
            self.is_loaded = False
            return False
    
    def _load_whisper_model(self):
        """Load Whisper model (runs in thread pool)"""
        # Suppress transformers logging
        import logging as tf_logging
        tf_logging.getLogger("transformers").setLevel(tf_logging.ERROR)
        
        return hf_pipeline(
            "automatic-speech-recognition",
            model=self.model_name,
            device=-1  # Use CPU
        )
    
    async def transcribe_audio_data(self, audio_data: np.ndarray, sample_rate: int) -> TranscriptionResult:
        """Transcribe numpy audio data"""
        if not self.is_loaded or not WHISPER_AVAILABLE:
            return TranscriptionResult(
                text="",
                confidence=0.0,
                duration=0.0,
                success=False,
                error="Whisper ASR not available"
            )
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Prepare audio for Whisper
            processed_audio = self._preprocess_audio(audio_data, sample_rate)
            audio_duration = len(processed_audio) / self.WHISPER_SAMPLE_RATE
            
            # Run transcription in thread pool
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._transcribe_sync, processed_audio
            )
            
            processing_duration = asyncio.get_event_loop().time() - start_time
            
            text = result.get('text', '').strip()
            
            return TranscriptionResult(
                text=text,
                confidence=0.8,  # Whisper doesn't provide confidence scores
                duration=processing_duration,
                success=bool(text),
                audio_duration=audio_duration
            )
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                duration=0.0,
                success=False,
                error=str(e)
            )
    
    async def transcribe_base64_audio(self, audio_base64: str, sample_rate: int, 
                                     audio_format: str = "float32") -> TranscriptionResult:
        """Transcribe base64 encoded audio data"""
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_base64)
            
            # Convert to numpy array based on format
            if audio_format == "float32":
                audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
            elif audio_format == "int16":
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                raise ValueError(f"Unsupported audio format: {audio_format}")
            
            return await self.transcribe_audio_data(audio_data, sample_rate)
            
        except Exception as e:
            self.logger.error(f"Failed to decode base64 audio: {e}")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                duration=0.0,
                success=False,
                error=f"Audio decoding failed: {str(e)}"
            )
    
    def _preprocess_audio(self, audio_data: np.ndarray, orig_sample_rate: int) -> np.ndarray:
        """Preprocess audio for Whisper (resample to 16kHz, normalize)"""
        # Resample if needed
        if orig_sample_rate != self.WHISPER_SAMPLE_RATE:
            audio_data = self._resample_audio(audio_data, orig_sample_rate, self.WHISPER_SAMPLE_RATE)
        
        # Ensure float32
        audio_data = audio_data.astype(np.float32)
        
        # Normalize audio
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data))
        
        return audio_data
    
    def _resample_audio(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple audio resampling using linear interpolation"""
        if orig_sr == target_sr:
            return audio
        
        ratio = target_sr / orig_sr
        new_length = int(len(audio) * ratio)
        
        # Linear interpolation
        indices = np.linspace(0, len(audio) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio)
        
        return resampled
    
    def _transcribe_sync(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Synchronous transcription (runs in thread pool)"""
        return self.whisper_pipeline(audio_data, sampling_rate=self.WHISPER_SAMPLE_RATE)
    
    def get_status(self) -> Dict[str, Any]:
        """Get transcription service status"""
        return {
            "whisper_available": WHISPER_AVAILABLE,
            "model_loaded": self.is_loaded,
            "model_name": self.model_name,
            "expected_sample_rate": self.WHISPER_SAMPLE_RATE
        }
    
    async def reload_model(self, model_name: Optional[str] = None) -> bool:
        """Reload Whisper model (optionally with different model)"""
        if model_name:
            self.model_name = model_name
        
        self.whisper_pipeline = None
        self.is_loaded = False
        
        return await self._initialize_whisper()