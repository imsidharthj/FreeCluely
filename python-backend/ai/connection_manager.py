"""
AI Connection Manager - Python equivalent of AIConnectionManager.swift
Handles OpenAI-based AI chat with streaming responses, message history, and reconnection
"""

import asyncio
import json
import os
import logging
import aiohttp
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import base64
import uuid

# Enhanced OpenAI import with debugging
try:
    import openai
    print(f"✅ OpenAI library found - Version: {openai.__version__}")
    
    # Version compatibility check
    from packaging import version
    openai_version = version.parse(openai.__version__)
    min_required = version.parse("1.12.0")
    
    if openai_version < min_required:
        print(f"⚠️  WARNING: OpenAI version {openai.__version__} is outdated. Minimum required: 1.12.0")
        print("   Some features may not work correctly. Please update with: pip install openai>=1.12.0")
    
    # Try importing AsyncOpenAI with detailed error handling
    try:
        from openai import AsyncOpenAI
        OPENAI_AVAILABLE = True
        print("✅ AsyncOpenAI imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import AsyncOpenAI: {e}")
        print("   This suggests an incompatible OpenAI library version")
        OPENAI_AVAILABLE = False
        AsyncOpenAI = None
    
except ImportError as e:
    print(f"❌ OpenAI library not found: {e}")
    print("   Install with: pip install openai>=1.12.0")
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None
    openai = None
except Exception as e:
    print(f"❌ Unexpected error importing OpenAI: {e}")
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None
    openai = None


@dataclass
class AIMessage:
    """AI message model"""
    role: str  # "user" or "assistant"
    content: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class AIMessageMetadata:
    """Metadata for AI messages"""
    ocr_text: Optional[str] = None
    selected_text: Optional[str] = None
    browser_url: Optional[str] = None


@dataclass
class AIRequest:
    """AI request model"""
    messages: List[Dict[str, Any]]
    image_bytes: Optional[str] = None  # Base64 encoded
    smarter_analysis_enabled: bool = False


@dataclass
class AIResponse:
    """AI response model"""
    content: str
    is_complete: bool = False


@dataclass
class MessageData:
    """UI message data"""
    id: str
    message: str
    is_user: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if not self.id:
            self.id = str(uuid.uuid4())


class AIConnectionManager:
    """Manages AI connection with streaming responses using OpenAI API"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Connection state
        self.is_connected: bool = False
        self.is_receiving: bool = False
        self.should_maintain_connection: bool = True
        self.openai_available: bool = OPENAI_AVAILABLE
        
        # OpenAI client configuration
        self.openai_client: Optional[AsyncOpenAI] = None
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        # Debug information
        print(f"🔧 AIConnectionManager initialized:")
        print(f"   OpenAI Available: {self.openai_available}")
        print(f"   API Key Present: {'✅' if self.api_key else '❌'}")
        print(f"   Model: {self.model}")
        print(f"   Base URL: {self.base_url}")
        
        if not self.openai_available:
            print("⚠️  AI functionality will be disabled due to missing OpenAI library")
        elif not self.api_key:
            print("⚠️  AI functionality will be disabled due to missing OPENAI_API_KEY")
        
        # Message handling
        self.message_stream: str = ""
        self.message_history: List[AIMessage] = []
        self.last_messages: List[MessageData] = []
        
        # Response completion tracking
        self._current_response_event: Optional[asyncio.Event] = None
        self._current_response_content: str = ""
        
        # Reconnection handling (for API health checks)
        self.reconnection_attempts: int = 0
        self.max_reconnection_attempts: int = 10
        self.reconnection_delay: float = 1.0
        
        # Background tasks
        self.health_check_task: Optional[asyncio.Task] = None
        
        # Callbacks
        self.on_message_received: Optional[Callable[[str], None]] = None
        self.on_connection_changed: Optional[Callable[[bool], None]] = None
        
        # Real-time streaming callbacks - NEW
        self.on_chunk_received: Optional[Callable[[str], None]] = None
        self.on_response_complete: Optional[Callable[[str], None]] = None
        self.on_thinking_changed: Optional[Callable[[bool], None]] = None
        self._generation_stopped = False

    def set_message_callback(self, callback: Callable[[str], None]):
        """Set callback for message updates"""
        self.on_message_received = callback
    
    def set_connection_callback(self, callback: Callable[[bool], None]]):
        """Set callback for connection state changes"""
        self.on_connection_changed = callback
    
    def set_streaming_callbacks(self, 
                               on_chunk: Optional[Callable[[str], None]] = None,
                               on_complete: Optional[Callable[[str], None]] = None,
                               on_thinking: Optional[Callable[[bool], None]] = None):
        """Set real-time streaming callbacks for chat interface"""
        self.on_chunk_received = on_chunk
        self.on_response_complete = on_complete
        self.on_thinking_changed = on_thinking
    
    def stop_generation(self):
        """Stop AI response generation"""
        self._generation_stopped = True
        if self.on_thinking_changed:
            self.on_thinking_changed(False)
    
    async def send_message_streaming(
        self,
        text: str,
        ocr_text: Optional[str] = None,
        selected_text: Optional[str] = None,
        browser_url: Optional[str] = None,
        image_data: Optional[bytes] = None,
        smarter_analysis_enabled: bool = False
    ):
        """Send message to OpenAI API with real-time streaming support"""
        if not self.is_connected:
            if self.should_maintain_connection:
                await self.connect()
            
            if not self.is_connected:
                raise ConnectionError("Not connected to OpenAI API")
        
        # Reset generation stop flag
        self._generation_stopped = False
        
        # Notify thinking started
        if self.on_thinking_changed:
            self.on_thinking_changed(True)
        
        # Add user message to history
        if self.message_stream:
            # Save previous assistant message
            self.last_messages.append(MessageData(
                id=str(uuid.uuid4()),
                message=self.message_stream,
                is_user=False
            ))
        
        # Add current user message
        self.last_messages.append(MessageData(
            id=str(uuid.uuid4()),
            message=text,
            is_user=True
        ))
        
        # Clear current stream
        self.message_stream = ""
        
        # Create enhanced prompt with context
        enhanced_prompt = self._create_enhanced_prompt(
            text, ocr_text, selected_text, browser_url, smarter_analysis_enabled
        )
        
        # Create message metadata
        metadata = AIMessageMetadata(
            ocr_text=ocr_text,
            selected_text=selected_text,
            browser_url=browser_url
        )
        
        # Create and store user message
        user_message = AIMessage(
            role="user",
            content=enhanced_prompt,
            metadata=asdict(metadata) if any([ocr_text, selected_text, browser_url]) else None
        )
        self.message_history.append(user_message)
        
        # Prepare messages for OpenAI API
        api_messages = self._prepare_api_messages(image_data)
        
        # Send request to OpenAI API with streaming
        self.is_receiving = True
        
        # Initialize response completion tracking
        self._current_response_event = asyncio.Event()
        self._current_response_content = ""
        
        try:
            await self._stream_openai_response_realtime(api_messages, smarter_analysis_enabled)
        except Exception as e:
            self.is_receiving = False
            if self.on_thinking_changed:
                self.on_thinking_changed(False)
            raise e
        
        # Wait for response to complete
        await self._current_response_event.wait()
        return self._current_response_content
    
    async def _stream_openai_response_realtime(self, messages: List[Dict[str, Any]], smarter_analysis: bool):
        """Stream response from OpenAI API with real-time callbacks"""
        try:
            # Use appropriate model based on smarter analysis
            model = "gpt-4" if smarter_analysis else self.model
            
            stream = await self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2000,
                temperature=0.7,
                stream=True
            )
            
            response_chunks = []
            
            async for chunk in stream:
                if self._generation_stopped:
                    break
                
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    self.message_stream += content
                    self._current_response_content += content
                    response_chunks.append(content)
                    
                    # Send real-time chunk to frontend
                    if self.on_chunk_received:
                        self.on_chunk_received(content)
                    
                    # Legacy callback for compatibility
                    if self.on_message_received:
                        self.on_message_received(self.message_stream)
                
                # Check if stream is finished
                if chunk.choices[0].finish_reason is not None:
                    self.is_receiving = False
                    
                    # Notify thinking stopped
                    if self.on_thinking_changed:
                        self.on_thinking_changed(False)
                    
                    # Add assistant message to history
                    assistant_message = AIMessage(
                        role="assistant",
                        content=self.message_stream
                    )
                    self.message_history.append(assistant_message)
                    
                    # Notify completion
                    if self.on_response_complete:
                        self.on_response_complete(self.message_stream)
                    
                    # Final callback with complete message
                    if self.on_message_received:
                        self.on_message_received(self.message_stream)
                    
                    # Signal response completion
                    self._current_response_event.set()
                    
                    break
                    
        except Exception as e:
            self.is_receiving = False
            if self.on_thinking_changed:
                self.on_thinking_changed(False)
            print(f"Error streaming OpenAI response: {e}")
            raise e

    async def connect(self):
        """Connect to OpenAI API service"""
        if not self.openai_available:
            self.logger.error("OpenAI library not available - cannot connect")
            self.is_connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False)
            return
        
        if not self.api_key:
            self.logger.error("OpenAI API key not provided - cannot connect")
            self.is_connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False)
            return
        
        try:
            self.logger.info("Connecting to OpenAI API...")
            
            # Initialize OpenAI client
            self.openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            # Test API connection with minimal request
            await self._test_api_connection()
            
            self.is_connected = True
            self.reconnection_attempts = 0
            
            # Start health check task
            if self.should_maintain_connection:
                self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.logger.info("✅ Successfully connected to OpenAI API")
            
            # Notify connection change
            if self.on_connection_changed:
                self.on_connection_changed(True)
                
        except Exception as e:
            self.logger.error(f"Failed to connect to OpenAI API: {e}")
            self.is_connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False)
            raise
    
    async def disconnect(self):
        """Disconnect from OpenAI API service"""
        self.logger.info("Disconnecting from OpenAI API...")
        
        self.should_maintain_connection = False
        self.is_connected = False
        
        # Cancel health check task
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None
        
        # Close OpenAI client
        if self.openai_client:
            await self.openai_client.close()
            self.openai_client = None
        
        self.logger.info("✅ Disconnected from OpenAI API")
        
        # Notify connection change
        if self.on_connection_changed:
            self.on_connection_changed(False)
    
    async def _test_api_connection(self):
        """Test OpenAI API connection with enhanced debugging"""
        try:
            self.logger.info("Testing OpenAI API connection...")
            
            # Test with minimal completion request (uses very few tokens)
            test_response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use cheaper model for testing
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,  # Minimal token usage
                temperature=0
            )
            
            if test_response and test_response.choices:
                self.logger.info("✅ OpenAI API connection test successful")
                return True
            else:
                raise Exception("API test returned empty response")
                
        except Exception as e:
            self.logger.error(f"OpenAI API connection test failed: {e}")
            raise
    
    async def _health_check_loop(self):
        """Background health check for API connection"""
        while self.should_maintain_connection and self.is_connected:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                if self.should_maintain_connection:
                    # Simple API health check
                    await self._test_api_connection()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning(f"Health check failed: {e}")
                if self.should_maintain_connection:
                    await self._attempt_reconnection()
    
    async def _attempt_reconnection(self):
        """Attempt to reconnect to OpenAI API"""
        if self.reconnection_attempts >= self.max_reconnection_attempts:
            self.logger.error("Max reconnection attempts reached")
            self.is_connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False)
            return
        
        self.reconnection_attempts += 1
        wait_time = min(self.reconnection_delay * (2 ** self.reconnection_attempts), 60)
        
        self.logger.info(f"Attempting reconnection {self.reconnection_attempts}/{self.max_reconnection_attempts} in {wait_time}s")
        await asyncio.sleep(wait_time)
        
        try:
            await self.connect()
        except Exception as e:
            self.logger.error(f"Reconnection attempt {self.reconnection_attempts} failed: {e}")
    
    def _create_enhanced_prompt(
        self, 
        text: str, 
        ocr_text: Optional[str], 
        selected_text: Optional[str], 
        browser_url: Optional[str],
        smarter_analysis: bool
    ) -> str:
        """Create enhanced prompt with context"""
        prompt_parts = [text]
        
        if ocr_text:
            prompt_parts.append(f"\n\nScreen OCR Text: {ocr_text}")
        
        if selected_text:
            prompt_parts.append(f"\n\nSelected Text: {selected_text}")
        
        if browser_url:
            prompt_parts.append(f"\n\nBrowser URL: {browser_url}")
        
        if smarter_analysis:
            prompt_parts.append("\n\nPlease provide a detailed and comprehensive analysis.")
        
        return "".join(prompt_parts)
    
    def _prepare_api_messages(self, image_data: Optional[bytes] = None) -> List[Dict[str, Any]]:
        """Prepare messages for OpenAI API"""
        api_messages = []
        
        # Convert message history to API format
        for msg in self.message_history[-10:]:  # Keep last 10 messages for context
            api_msg = {
                "role": msg.role,
                "content": msg.content
            }
            api_messages.append(api_msg)
        
        # Add image if provided
        if image_data and len(api_messages) > 0:
            # Add image to the last user message
            last_msg = api_messages[-1]
            if last_msg["role"] == "user":
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                last_msg["content"] = [
                    {"type": "text", "text": last_msg["content"]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
        
        return api_messages
    
    async def send_message(
        self,
        text: str,
        ocr_text: Optional[str] = None,
        selected_text: Optional[str] = None,
        browser_url: Optional[str] = None,
        image_data: Optional[bytes] = None,
        smarter_analysis_enabled: bool = False
    ):
        """
        Send message to OpenAI API
        
        Args:
            text: User message text
            ocr_text: OCR text from screen
            selected_text: Selected text
            browser_url: Current browser URL
            image_data: Screenshot image data
            smarter_analysis_enabled: Enable advanced analysis
        """
        if not self.is_connected:
            if self.should_maintain_connection:
                await self.connect()
            
            if not self.is_connected:
                raise ConnectionError("Not connected to OpenAI API")
        
        # Add user message to history
        if self.message_stream:
            # Save previous assistant message
            self.last_messages.append(MessageData(
                id=str(uuid.uuid4()),
                message=self.message_stream,
                is_user=False
            ))
        
        # Add current user message
        self.last_messages.append(MessageData(
            id=str(uuid.uuid4()),
            message=text,
            is_user=True
        ))
        
        # Clear current stream
        self.message_stream = ""
        
        # Create enhanced prompt with context
        enhanced_prompt = self._create_enhanced_prompt(
            text, ocr_text, selected_text, browser_url, smarter_analysis_enabled
        )
        
        # Create message metadata
        metadata = AIMessageMetadata(
            ocr_text=ocr_text,
            selected_text=selected_text,
            browser_url=browser_url
        )
        
        # Create and store user message
        user_message = AIMessage(
            role="user",
            content=enhanced_prompt,
            metadata=asdict(metadata) if any([ocr_text, selected_text, browser_url]) else None
        )
        self.message_history.append(user_message)
        
        # Prepare messages for OpenAI API
        api_messages = self._prepare_api_messages(image_data)
        
        # Send request to OpenAI API with streaming
        self.is_receiving = True
        
        # Initialize response completion tracking
        self._current_response_event = asyncio.Event()
        self._current_response_content = ""
        
        try:
            await self._stream_openai_response(api_messages, smarter_analysis_enabled)
        except Exception as e:
            self.is_receiving = False
            raise e
        
        # Wait for response to complete
        await self._current_response_event.wait()
        return self._current_response_content
    
    async def _stream_openai_response(self, messages: List[Dict[str, Any]], smarter_analysis: bool):
        """Stream response from OpenAI API"""
        try:
            # Use appropriate model based on smarter analysis
            model = "gpt-4" if smarter_analysis else self.model
            
            stream = await self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2000,
                temperature=0.7,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    self.message_stream += content
                    self._current_response_content += content
                    
                    # Legacy callback for compatibility
                    if self.on_message_received:
                        self.on_message_received(self.message_stream)
                
                # Check if stream is finished
                if chunk.choices[0].finish_reason is not None:
                    self.is_receiving = False
                    
                    # Add assistant message to history
                    assistant_message = AIMessage(
                        role="assistant",
                        content=self.message_stream
                    )
                    self.message_history.append(assistant_message)
                    
                    # Final callback with complete message
                    if self.on_message_received:
                        self.on_message_received(self.message_stream)
                    
                    # Signal response completion
                    self._current_response_event.set()
                    break
                    
        except Exception as e:
            self.is_receiving = False
            print(f"Error streaming OpenAI response: {e}")
            raise e
    
    def get_status(self) -> Dict[str, Any]:
        """Get connection status"""
        return {
            "connected": self.is_connected,
            "receiving": self.is_receiving,
            "openai_available": self.openai_available,
            "api_key_present": bool(self.api_key),
            "model": self.model,
            "message_count": len(self.message_history),
            "stream_length": len(self.message_stream)
        }
    
    def get_message_history(self) -> List[Dict[str, Any]]:
        """Get message history for UI"""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "metadata": msg.metadata
            }
            for msg in self.message_history
        ]
    
    def get_last_messages(self) -> List[Dict[str, Any]]:
        """Get last messages for UI"""
        return [
            {
                "id": msg.id,
                "message": msg.message,
                "is_user": msg.is_user,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
            }
            for msg in self.last_messages
        ]
    
    def clear_conversation(self):
        """Clear conversation history"""
        self.message_history.clear()
        self.last_messages.clear()
        self.message_stream = ""
        self._current_response_content = ""