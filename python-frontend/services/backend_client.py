"""
Backend client for communication with the Python backend service
"""

import logging
import asyncio
import json
from typing import Optional, Dict, Any, Callable
import aiohttp
import websockets
from dataclasses import dataclass

from config.settings import BackendConfig


@dataclass
class APIResponse:
    """Represents an API response"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class BackendClient:
    """Client for communicating with the Python backend"""
    
    def __init__(self, base_url: str = "http://103.42.50.224:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws") + "/ws"
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.websocket_connected = False
        self.logger = logging.getLogger(__name__)
        
        # Message handlers for WebSocket responses
        self.message_handlers: Dict[str, Callable] = {}
        self.websocket_task: Optional[asyncio.Task] = None
        
        # Connection state
        self.connected = False
        self.reconnect_attempts = 0
        
        # Configuration
        self.config = BackendConfig()
        self.config.base_url = base_url
        self.config.api_timeout = 30
        self.config.reconnect_attempts = 3
    
    async def connect(self):
        """Connect to the backend service"""
        self.logger.info("Connecting to backend service")
        
        try:
            # Create HTTP session
            timeout = aiohttp.ClientTimeout(total=self.config.api_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            # Test HTTP connection - use correct health endpoint
            health_response = await self.get("/api/v1/health")
            if not health_response.success:
                raise Exception("Backend health check failed")
            
            # Connect WebSocket for real-time AI streaming
            await self._connect_websocket()
            
            self.connected = True
            self.reconnect_attempts = 0
            self.logger.info("Successfully connected to backend with WebSocket support")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to backend: {e}")
            await self.disconnect()
            raise
    
    async def disconnect(self):
        """Disconnect from the backend service"""
        self.logger.info("Disconnecting from backend service")
        self.connected = False
        
        # Close WebSocket
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _connect_websocket(self):
        """Connect to WebSocket endpoint"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.websocket_connected = True
            self.websocket_task = asyncio.create_task(self._websocket_listener())
            self.logger.info("WebSocket connected")
        except Exception as e:
            self.logger.error(f"Failed to connect WebSocket: {e}")
            raise
    
    async def _websocket_listener(self):
        """Listen for WebSocket messages"""
        try:
            while self.websocket_connected and self.websocket:
                try:
                    message = await self.websocket.recv()
                    await self._handle_websocket_message(message)
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("WebSocket connection closed")
                    break
                except Exception as e:
                    self.logger.error(f"Error in WebSocket listener: {e}")
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self.websocket_connected = False
    
    async def _handle_websocket_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type in self.message_handlers:
                handler = self.message_handlers[message_type]
                # Get the data payload for the handler
                payload = data.get('data', data)
                
                # Check if handler is async
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)  # Call synchronously
            else:
                self.logger.debug(f"No handler for message type: {message_type}")
                
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _reconnect_websocket(self):
        """Attempt to reconnect WebSocket"""
        if self.reconnect_attempts >= self.config.reconnect_attempts:
            self.logger.error("Max reconnect attempts reached")
            return
        
        self.reconnect_attempts += 1
        wait_time = min(2 ** self.reconnect_attempts, 30)  # Exponential backoff
        
        self.logger.info(f"Reconnecting WebSocket in {wait_time}s (attempt {self.reconnect_attempts})")
        await asyncio.sleep(wait_time)
        
        try:
            await self._connect_websocket()
            self.reconnect_attempts = 0
            self.logger.info("WebSocket reconnected successfully")
        except Exception as e:
            self.logger.error(f"WebSocket reconnect failed: {e}")
            asyncio.create_task(self._reconnect_websocket())
    
    # HTTP API methods
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> APIResponse:
        """Make GET request"""
        return await self._request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make POST request"""
        return await self._request("POST", endpoint, json=data)
    
    async def put(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make PUT request"""
        return await self._request("PUT", endpoint, json=data)
    
    async def delete(self, endpoint: str) -> APIResponse:
        """Make DELETE request"""
        return await self._request("DELETE", endpoint)
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> APIResponse:
        """Make HTTP request"""
        if not self.session:
            return APIResponse(success=False, error="Not connected")
        
        url = f"{self.config.base_url}{endpoint}"
        
        try:
            async with self.session.request(method, url, **kwargs) as response:
                if response.content_type == 'application/json':
                    data = await response.json()
                else:
                    data = await response.text()
                
                if response.status < 400:
                    return APIResponse(success=True, data=data, status_code=response.status)
                else:
                    error_msg = data.get('error', f"HTTP {response.status}") if isinstance(data, dict) else str(data)
                    return APIResponse(success=False, error=error_msg, status_code=response.status)
                    
        except Exception as e:
            self.logger.error(f"Request failed: {method} {url} - {e}")
            return APIResponse(success=False, error=str(e))
    
    async def post_form(self, endpoint: str, data: Optional[Dict] = None) -> APIResponse:
        """Make POST request with form data"""
        return await self._request("POST", endpoint, data=data)

    # WebSocket methods
    async def send_websocket_message(self, message: Dict[str, Any]):
        """Send message via WebSocket"""
        if not self.websocket:
            self.logger.error("WebSocket not connected")
            return
        
        try:
            await self.websocket.send(json.dumps(message))
            self.logger.debug(f"Sent WebSocket message: {message.get('type', 'unknown')}")
        except Exception as e:
            self.logger.error(f"Failed to send WebSocket message: {e}")
    
    def register_message_handler(self, message_type: str, handler: Callable):
        """Register handler for WebSocket message type"""
        self.message_handlers[message_type] = handler
        self.logger.debug(f"Registered handler for message type: {message_type}")
    
    # AI/Chat specific methods - Updated to match backend
    async def send_ai_message(self, text: str, smarter_analysis: bool = False) -> APIResponse:
        """Send message to AI using query parameters to match FastAPI expectations"""
        params = {
            'text': text,
            'smarter_analysis': str(smarter_analysis).lower()  # Convert boolean to FastAPI-compatible string
        }
        # Use _request directly with params keyword to send as query parameters
        return await self._request("POST", "/api/v1/ai/send-message", params=params)
    
    async def get_ai_status(self) -> APIResponse:
        """Get AI connection status"""
        return await self.get("/api/v1/ai/status")
    
    async def get_ai_messages(self) -> APIResponse:
        """Get AI message history"""
        return await self.get("/api/v1/ai/messages")
    
    async def clear_ai_conversation(self) -> APIResponse:
        """Clear AI conversation history"""
        return await self.post("/api/v1/ai/clear-conversation")
    
    # Legacy chat methods for backward compatibility
    async def send_chat_message(self, message: str, context: Optional[Dict] = None, smarter_analysis: bool = False) -> APIResponse:
        """Legacy method - redirects to send_ai_message"""
        return await self.send_ai_message(message, smarter_analysis)
    
    async def get_chat_history(self) -> APIResponse:
        """Legacy method - redirects to get_ai_messages"""
        return await self.get_ai_messages()
    
    async def clear_chat_history(self) -> APIResponse:
        """Legacy method - redirects to clear_ai_conversation"""
        return await self.clear_ai_conversation()
    
    # Context specific methods - Updated to match backend
    async def capture_context(self, capture_image: bool = True) -> APIResponse:
        """Capture current context"""
        params = {'capture_image': capture_image}
        return await self.post("/api/v1/context/capture", params)
    
    async def search_context(self, ocr_text: str, method: str = "sentence_chunks") -> APIResponse:
        """Search for context based on OCR text"""
        params = {
            'ocr_text': ocr_text,
            'method': method
        }
        return await self.post("/api/v1/context/search", params)
    
    async def get_context_notes(self) -> APIResponse:
        """Get current context notes"""
        return await self.get("/api/v1/context/notes")
    
    # Legacy context methods for backward compatibility
    async def get_context_suggestions(self, query: str) -> APIResponse:
        """Legacy method - redirects to search_context"""
        return await self.search_context(query)
    
    # Tag management methods - New methods to match backend
    async def get_all_tags(self) -> APIResponse:
        """Get all tags"""
        return await self.get("/api/v1/tags")
    
    async def search_tags(self, query: str) -> APIResponse:
        """Search tags by name"""
        params = {'query': query}
        return await self.get("/api/v1/tags/search", params)
    
    async def get_tag(self, tag_id: str) -> APIResponse:
        """Get specific tag by ID"""
        return await self.get(f"/api/v1/tags/{tag_id}")
    
    async def refresh_tags(self) -> APIResponse:
        """Refresh tags from server"""
        return await self.post("/api/v1/tags/refresh")
    
    async def get_tag_status(self) -> APIResponse:
        """Get tag manager status"""
        return await self.get("/api/v1/tags/status")
    
    # Overlay management methods - New methods to match backend
    async def toggle_ai_assist_overlay(self) -> APIResponse:
        """Toggle AI Assist overlay"""
        return await self.post("/api/v1/overlay/ai-assist/toggle")
    
    async def toggle_auto_context_overlay(self) -> APIResponse:
        """Toggle Auto Context overlay"""
        return await self.post("/api/v1/overlay/auto-context/toggle")
    
    async def toggle_quick_capture_overlay(self) -> APIResponse:
        """Toggle Quick Capture overlay"""
        return await self.post("/api/v1/overlay/quick-capture/toggle")
    
    async def get_overlay_states(self) -> APIResponse:
        """Get current overlay states"""
        return await self.get("/api/v1/overlay/states")
    
    # Auth methods - Updated to match backend
    async def login(self, token: str) -> APIResponse:
        """Login to backend using token"""
        params = {'token': token}
        return await self.post("/api/v1/auth/login", params)
    
    async def logout(self) -> APIResponse:
        """Logout from backend"""
        return await self.post("/api/v1/auth/logout")
    
    async def get_auth_status(self) -> APIResponse:
        """Get authentication status"""
        return await self.get("/api/v1/auth/status")
    
    # Legacy auth methods for backward compatibility
    async def get_user_info(self) -> APIResponse:
        """Legacy method - redirects to get_auth_status"""
        return await self.get_auth_status()
    
    # Hotkey management methods - New methods to match backend
    async def get_hotkeys(self) -> APIResponse:
        """Get current hotkey shortcuts"""
        return await self.get("/api/v1/hotkeys")
    
    async def update_hotkey(self, action: str, key: str, modifiers: list) -> APIResponse:
        """Update hotkey shortcut for an action"""
        data = {
            'key': key,
            'modifiers': modifiers
        }
        return await self.post(f"/api/v1/hotkeys/{action}", data)
    
    # System status method - New method to match backend
    async def get_system_status(self) -> APIResponse:
        """Get comprehensive system status"""
        return await self.get("/api/v1/system/status")
    
    # Screenshot processing methods - New methods for Option 1 implementation
    async def process_screenshot(self, image_data: str, preprocess: bool = True, extract_blocks: bool = False) -> APIResponse:
        """
        Process screenshot with OCR using simple JSON endpoint
        
        Args:
            image_data: Base64 encoded image data
            preprocess: Whether to apply image preprocessing for better OCR
            extract_blocks: Whether to extract structured text blocks
            
        Returns:
            APIResponse with OCR results
        """
        data = {
            "image_data": image_data,
            "preprocess": preprocess,
            "extract_blocks": extract_blocks
        }
        return await self.post("/api/v1/context/process-screenshot-simple", data)
    
    async def process_screenshot_file(self, image_file_path: str, preprocess: bool = True, extract_blocks: bool = False) -> APIResponse:
        """
        Process screenshot file with OCR using multipart upload
        
        Args:
            image_file_path: Path to image file
            preprocess: Whether to apply image preprocessing for better OCR
            extract_blocks: Whether to extract structured text blocks
            
        Returns:
            APIResponse with OCR results
        """
        try:
            import aiofiles
            
            async with aiofiles.open(image_file_path, 'rb') as f:
                file_data = await f.read()
            
            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field('preprocess', str(preprocess).lower())
            data.add_field('extract_blocks', str(extract_blocks).lower())
            data.add_field('image_file', file_data, 
                          filename=image_file_path.split('/')[-1],
                          content_type='image/png')
            
            # Make request with multipart data
            if not self.session:
                raise Exception("Backend client not connected")
            
            url = f"{self.config.base_url}/api/v1/context/process-screenshot"
            
            async with self.session.post(url, data=data) as response:
                response_data = await response.json()
                
                return APIResponse(
                    success=response.status == 200,
                    data=response_data.get('data') if response.status == 200 else None,
                    error=response_data.get('detail') if response.status != 200 else None,
                    status_code=response.status
                )
                
        except Exception as e:
            self.logger.error(f"Failed to process screenshot file: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )
    
    async def capture_and_process_context(self, include_screenshot: bool = True) -> APIResponse:
        """
        Enhanced context capture that can include frontend screenshot processing
        
        Args:
            include_screenshot: Whether to capture and process screenshot from frontend
            
        Returns:
            APIResponse with complete context data including OCR results
        """
        try:
            context_data = {}
            
            if include_screenshot:
                # This would be called by a screenshot manager
                # For now, just capture context normally
                response = await self.capture_context(capture_image=True)
                if response.success:
                    context_data.update(response.data)
            else:
                # Capture context without screenshot
                response = await self.capture_context(capture_image=False)
                if response.success:
                    context_data.update(response.data)
            
            return APIResponse(
                success=True,
                data=context_data,
                error=None,
                status_code=200
            )
            
        except Exception as e:
            self.logger.error(f"Failed to capture and process context: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )
    
    # Quick Capture specific methods
    async def take_screenshot(self) -> APIResponse:
        """Take a screenshot using the backend"""
        try:
            return await self.post("/api/v1/capture/screenshot")
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )

    async def save_capture(self, image_data: str, metadata: Optional[Dict] = None) -> APIResponse:
        """Save captured image with metadata"""
        try:
            data = {
                'image_data': image_data,
                'metadata': metadata or {}
            }
            return await self.post("/api/v1/capture/save", data)
        except Exception as e:
            self.logger.error(f"Failed to save capture: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )

    # Auto Context specific methods
    async def search_context(self, query: str, method: str = "sentence_chunks") -> APIResponse:
        """Search for relevant context using the query"""
        try:
            params = {
                'query': query,
                'method': method
            }
            return await self.post("/api/v1/context/search", params)
        except Exception as e:
            self.logger.error(f"Failed to search context: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )

    async def get_context_history(self) -> APIResponse:
        """Get context search history"""
        try:
            return await self.get("/api/v1/context/history")
        except Exception as e:
            self.logger.error(f"Failed to get context history: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )

    # Voice Transcription methods - NEW
    async def transcribe_voice(self, audio_data: str, sample_rate: int = 16000, audio_format: str = "float32") -> APIResponse:
        """Transcribe audio data to text using backend Whisper service"""
        try:
            params = {
                'audio_data': audio_data,
                'sample_rate': sample_rate,
                'audio_format': audio_format
            }
            return await self.post("/api/v1/voice/transcribe", params)
        except Exception as e:
            self.logger.error(f"Failed to transcribe voice: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )
    
    async def transcribe_and_send_voice(self, audio_data: str, sample_rate: int = 16000, 
                                       audio_format: str = "float32", audio_source: str = "microphone",
                                       smarter_analysis: bool = False) -> APIResponse:
        """Transcribe audio and automatically send to AI with context"""
        try:
            params = {
                'audio_data': audio_data,
                'sample_rate': sample_rate,
                'audio_format': audio_format,
                'audio_source': audio_source,
                'smarter_analysis': smarter_analysis
            }
            return await self.post("/api/v1/voice/transcribe-and-send", params)
        except Exception as e:
            self.logger.error(f"Failed to transcribe and send voice: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )
    
    async def get_voice_status(self) -> APIResponse:
        """Get voice transcription service status"""
        try:
            return await self.get("/api/v1/voice/status")
        except Exception as e:
            self.logger.error(f"Failed to get voice status: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )
    
    async def reload_whisper_model(self, model_name: Optional[str] = None) -> APIResponse:
        """Reload Whisper model with optional different model"""
        try:
            data = {}
            if model_name:
                data['model_name'] = model_name
            return await self.post("/api/v1/voice/reload-model", data)
        except Exception as e:
            self.logger.error(f"Failed to reload Whisper model: {e}")
            return APIResponse(
                success=False,
                data=None,
                error=str(e),
                status_code=500
            )