"""
Voice input management using sounddevice and backend transcription API
Frontend handles audio capture, backend handles Whisper transcription
"""

import logging
import asyncio
import threading
from typing import Optional, Callable, List
import queue
import numpy as np
import sounddevice as sd
import base64
from dataclasses import dataclass

from config.settings import AudioConfig

@dataclass
class AudioChunk:
    """Represents an audio data chunk"""
    data: np.ndarray
    timestamp: float
    sample_rate: int

@dataclass
class VoiceTranscription:
    """Represents a voice transcription result from backend"""
    text: str
    confidence: float
    duration: float
    success: bool
    error: Optional[str] = None
    audio_duration: Optional[float] = None

class VoiceInputManager:
    """Manages voice input capture and sends to backend for transcription"""
    
    def __init__(self, audio_config: AudioConfig, capture_system_audio: bool = False):
        self.config = audio_config
        self.logger = logging.getLogger(__name__)
        
        # Audio source type
        self.capture_system_audio = capture_system_audio
        self.audio_source_name = "System Audio" if capture_system_audio else "Microphone"
        
        # Recording state
        self.is_recording = False
        self.stream: Optional[sd.InputStream] = None
        self.audio_queue = queue.Queue()
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable[[AudioChunk], None]] = None
        self.on_voice_detected: Optional[Callable[[], None]] = None
        self.on_voice_ended: Optional[Callable[[], None]] = None
        self.on_transcription_ready: Optional[Callable[[VoiceTranscription], None]] = None
        
        # Voice activity detection
        self.vad_enabled = True
        self.silence_threshold = 0.01  # RMS threshold for silence
        self.min_voice_duration = 0.5  # Minimum seconds for voice detection
        self.silence_duration = 1.0    # Seconds of silence before voice end
        
        # Internal state
        self._voice_detected = False
        self._silence_counter = 0
        self._voice_samples = []
        
        # Backend integration (no local Whisper)
        self.backend_client = None  # Will be injected
        self.auto_send_to_ai = True
        
        # Log audio source
        self.logger.info(f"VoiceInputManager initialized for {self.audio_source_name}")
    
    def set_backend_client(self, client):
        """Set backend client for transcription and AI communication"""
        self.backend_client = client
    
    def configure_voice_to_ai(self, auto_send: bool = True):
        """Configure voice-to-AI pipeline"""
        self.auto_send_to_ai = auto_send
        self.logger.info(f"Voice-to-AI configured: auto_send={auto_send}")
    
    def list_devices(self) -> List[dict]:
        """List available audio devices (microphone or system monitor devices)"""
        try:
            devices = sd.query_devices()
            device_list = []
            
            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    device_name = device['name'].lower()
                    
                    if self.capture_system_audio:
                        # Look for monitor/loopback devices for system audio
                        if ('.monitor' in device_name or 
                            'loopback' in device_name or 
                            'sink.monitor' in device_name or
                            'what-u-hear' in device_name or
                            'stereo mix' in device_name):
                            device_list.append({
                                'id': i,
                                'name': device['name'],
                                'channels': device['max_input_channels'],
                                'sample_rate': device['default_samplerate'],
                                'type': 'monitor'
                            })
                    else:
                        # Regular microphone devices (exclude monitor devices)
                        if not any(pattern in device_name for pattern in 
                                 ['.monitor', 'loopback', 'sink.monitor']):
                            device_list.append({
                                'id': i,
                                'name': device['name'],
                                'channels': device['max_input_channels'],
                                'sample_rate': device['default_samplerate'],
                                'type': 'input'
                            })
            
            self.logger.info(f"Found {len(device_list)} {self.audio_source_name.lower()} devices")
            return device_list
            
        except Exception as e:
            self.logger.error(f"Failed to list {self.audio_source_name.lower()} devices: {e}")
            return []
    
    def get_default_device(self) -> Optional[dict]:
        """Get default device (microphone or best monitor device)"""
        try:
            if self.capture_system_audio:
                # For system audio, find the best monitor device
                available_devices = self.list_devices()
                if available_devices:
                    # Prefer devices with 'analog-stereo.monitor' in name
                    for device in available_devices:
                        if 'analog-stereo.monitor' in device['name'].lower():
                            return device
                    # Fallback to first available monitor device
                    return available_devices[0]
                return None
            else:
                # Regular microphone device selection
                device_id = sd.default.device[0]  # Input device
                device_info = sd.query_devices(device_id)
                
                return {
                    'id': device_id,
                    'name': device_info['name'],
                    'channels': device_info['max_input_channels'],
                    'sample_rate': device_info['default_samplerate'],
                    'type': 'input'
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get default {self.audio_source_name.lower()} device: {e}")
            return None
    
    async def start_recording(self) -> bool:
        """Start audio recording from microphone or system audio"""
        if self.is_recording:
            self.logger.warning(f"{self.audio_source_name} recording already in progress")
            return True
        
        try:
            self.logger.info(f"Starting {self.audio_source_name.lower()} recording")
            
            # Configure device
            device_id = self.config.device_id
            if device_id is None:
                # Use default device (mic or monitor)
                default_device = self.get_default_device()
                if default_device:
                    device_id = default_device['id']
                    self.logger.info(f"Using {self.audio_source_name.lower()} device: {default_device['name']}")
                else:
                    self.logger.error(f"No {self.audio_source_name.lower()} device available")
                    return False
            
            # Create input stream
            self.stream = sd.InputStream(
                device=device_id,
                channels=self.config.channels,
                samplerate=self.config.sample_rate,
                blocksize=self.config.chunk_size,
                callback=self._audio_callback,
                dtype=np.float32
            )
            
            # Start the stream
            self.stream.start()
            self.is_recording = True
            
            # Start processing in background
            asyncio.create_task(self._process_audio())
            
            self.logger.info(f"Recording started on device {device_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            return False
    
    async def stop_recording(self):
        """Stop audio recording"""
        if not self.is_recording:
            return
        
        self.logger.info("Stopping voice input recording")
        self.is_recording = False
        
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        # Clear any remaining audio
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
    
    def _audio_callback(self, indata: np.ndarray, frames: int, time, status):
        """Callback for audio stream"""
        if status:
            self.logger.warning(f"Audio callback status: {status}")
        
        if self.is_recording:
            # Copy audio data and add to queue
            audio_chunk = AudioChunk(
                data=indata.copy(),
                timestamp=time.inputBufferAdcTime,
                sample_rate=self.config.sample_rate
            )
            
            try:
                self.audio_queue.put_nowait(audio_chunk)
            except queue.Full:
                self.logger.warning("Audio queue full, dropping chunk")
    
    async def _process_audio(self):
        """Process audio chunks from queue"""
        while self.is_recording:
            try:
                # Get audio chunk with timeout
                chunk = await asyncio.get_event_loop().run_in_executor(
                    None, self._get_audio_chunk, 0.1
                )
                
                if chunk is None:
                    continue
                
                # Process the chunk
                await self._handle_audio_chunk(chunk)
                
            except Exception as e:
                self.logger.error(f"Error processing audio: {e}")
                await asyncio.sleep(0.1)
    
    def _get_audio_chunk(self, timeout: float) -> Optional[AudioChunk]:
        """Get audio chunk from queue with timeout"""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    async def _handle_audio_chunk(self, chunk: AudioChunk):
        """Handle individual audio chunk"""
        # Call callback if registered
        if self.on_audio_chunk:
            try:
                self.on_audio_chunk(chunk)
            except Exception as e:
                self.logger.error(f"Error in audio chunk callback: {e}")
        
        # Voice Activity Detection
        if self.vad_enabled:
            await self._process_vad(chunk)
    
    async def _process_vad(self, chunk: AudioChunk):
        """Process Voice Activity Detection"""
        # Calculate RMS (Root Mean Square) for volume level
        rms = np.sqrt(np.mean(chunk.data ** 2))
        
        is_voice = rms > self.silence_threshold
        
        if is_voice:
            self._silence_counter = 0
            self._voice_samples.append(chunk)
            
            # Check if voice just started
            if not self._voice_detected:
                # Check if we have enough samples for minimum duration
                total_duration = len(self._voice_samples) * self.config.chunk_size / self.config.sample_rate
                
                if total_duration >= self.min_voice_duration:
                    self._voice_detected = True
                    self.logger.debug("Voice activity detected")
                    
                    if self.on_voice_detected:
                        try:
                            self.on_voice_detected()
                        except Exception as e:
                            self.logger.error(f"Error in voice detected callback: {e}")
        else:
            # Silence detected
            self._silence_counter += 1
            silence_duration = self._silence_counter * self.config.chunk_size / self.config.sample_rate
            
            if self._voice_detected and silence_duration >= self.silence_duration:
                # Voice activity ended
                self._voice_detected = False
                self._silence_counter = 0
                
                self.logger.debug("Voice activity ended")
                
                # Process voice via backend transcription
                if self._voice_samples:
                    asyncio.create_task(self._process_voice_via_backend())
                
                if self.on_voice_ended:
                    try:
                        self.on_voice_ended()
                    except Exception as e:
                        self.logger.error(f"Error in voice ended callback: {e}")
                
                # Clear voice samples
                self._voice_samples.clear()
    
    async def _process_voice_via_backend(self):
        """Process collected voice samples via backend transcription API"""
        try:
            if not self.backend_client or not self._voice_samples:
                return
            
            # Get audio data
            audio_data = self.get_voice_audio()
            if audio_data is None or len(audio_data) == 0:
                return
            
            self.logger.info("Sending voice to backend for transcription...")
            
            # Encode audio as base64
            audio_bytes = audio_data.astype(np.float32).tobytes()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Determine audio source
            audio_source = "system_audio" if self.capture_system_audio else "microphone"
            
            # Send to backend for transcription and AI processing
            if self.auto_send_to_ai:
                # Use transcribe-and-send endpoint
                response = await self.backend_client.transcribe_and_send_voice(
                    audio_data=audio_base64,
                    sample_rate=self.config.sample_rate,
                    audio_format="float32",
                    audio_source=audio_source,
                    smarter_analysis=self.capture_system_audio
                )
                
                if response.success:
                    transcription_data = response.data.get('transcription', {})
                    ai_response_data = response.data.get('ai_response', {})
                    
                    # Create transcription result
                    transcription = VoiceTranscription(
                        text=transcription_data.get('text', ''),
                        confidence=transcription_data.get('confidence', 0.0),
                        duration=transcription_data.get('processing_duration', 0.0),
                        success=True,
                        audio_duration=transcription_data.get('audio_duration')
                    )
                    
                    self.logger.info(f"Transcription and AI response: '{transcription.text}' -> AI responded")
                    
                    # Trigger transcription callback
                    if self.on_transcription_ready:
                        try:
                            self.on_transcription_ready(transcription)
                        except Exception as e:
                            self.logger.error(f"Error in transcription callback: {e}")
                else:
                    self.logger.error(f"Backend transcription failed: {response.error}")
            else:
                # Use transcribe-only endpoint
                response = await self.backend_client.transcribe_voice(
                    audio_data=audio_base64,
                    sample_rate=self.config.sample_rate,
                    audio_format="float32"
                )
                
                if response.success and response.data:
                    transcription = VoiceTranscription(
                        text=response.data.get('text', ''),
                        confidence=response.data.get('confidence', 0.0),
                        duration=response.data.get('processing_duration', 0.0),
                        success=True,
                        audio_duration=response.data.get('audio_duration'),
                        error=response.data.get('error')
                    )
                    
                    self.logger.info(f"Transcription: '{transcription.text}'")
                    
                    # Trigger transcription callback
                    if self.on_transcription_ready:
                        try:
                            self.on_transcription_ready(transcription)
                        except Exception as e:
                            self.logger.error(f"Error in transcription callback: {e}")
                else:
                    self.logger.error(f"Backend transcription failed: {response.error}")
            
        except Exception as e:
            self.logger.error(f"Error in backend voice processing: {e}")
        finally:
            # Clear voice samples
            self._voice_samples.clear()
    
    def get_voice_audio(self) -> Optional[np.ndarray]:
        """Get collected voice audio data"""
        if not self._voice_samples:
            return None
        
        # Concatenate all voice samples
        audio_data = np.concatenate([chunk.data.flatten() for chunk in self._voice_samples])
        return audio_data
    
    def clear_voice_buffer(self):
        """Clear the voice sample buffer"""
        self._voice_samples.clear()
        self._voice_detected = False
        self._silence_counter = 0
    
    def set_callbacks(self, 
                     on_audio_chunk: Optional[Callable[[AudioChunk], None]] = None,
                     on_voice_detected: Optional[Callable[[], None]] = None,
                     on_voice_ended: Optional[Callable[[], None]] = None,
                     on_transcription_ready: Optional[Callable[[VoiceTranscription], None]] = None):
        """Set callback functions"""
        self.on_audio_chunk = on_audio_chunk
        self.on_voice_detected = on_voice_detected
        self.on_voice_ended = on_voice_ended
        self.on_transcription_ready = on_transcription_ready
    
    def configure_vad(self, 
                     silence_threshold: float = 0.01,
                     min_voice_duration: float = 0.5,
                     silence_duration: float = 1.0):
        """Configure Voice Activity Detection parameters"""
        self.silence_threshold = silence_threshold
        self.min_voice_duration = min_voice_duration
        self.silence_duration = silence_duration
        
        self.logger.info(f"VAD configured: threshold={silence_threshold}, "
                        f"min_duration={min_voice_duration}, silence={silence_duration}")
    
    def get_audio_level(self) -> float:
        """Get current audio level (0.0 to 1.0)"""
        if not self._voice_samples:
            return 0.0
        
        # Get RMS of last chunk
        last_chunk = self._voice_samples[-1]
        rms = np.sqrt(np.mean(last_chunk.data ** 2))
        
        # Normalize to 0-1 range (assuming max RMS of 0.5)
        return min(rms * 2.0, 1.0)
    
    def is_voice_active(self) -> bool:
        """Check if voice is currently being detected"""
        return self._voice_detected
    
    def get_voice_status(self) -> dict:
        """Get voice input status"""
        return {
            'backend_transcription': True,  # Using backend for transcription
            'local_whisper': False,  # No local Whisper
            'backend_client_set': self.backend_client is not None,
            'auto_send_to_ai': self.auto_send_to_ai,
            'is_recording': self.is_recording,
            'voice_detected': self._voice_detected,
            'voice_samples_count': len(self._voice_samples),
            'capture_system_audio': self.capture_system_audio,
            'audio_source': self.audio_source_name
        }