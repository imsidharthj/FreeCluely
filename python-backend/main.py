#!/usr/bin/env python3
"""
Main FastAPI server for Horizon AI Assistant Backend
Converts Swift ConstellaHorizonApp.swift to Python FastAPI
"""

import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Core service managers
from services.context_manager import AIContextManager
from services.auth_manager import AuthManager
from services.transcription_service import TranscriptionService  # NEW: Voice transcription
# REMOVED: from services.overlay_manager import OverlayManager - Overlays now handled by frontend

# AI and WebSocket managers
from ai.connection_manager import AIConnectionManager
from ai.tag_websocket_manager import TagWebSocketManager
from api.context_search import AutoContextManager
from api.routes import api_router

# Keep only essential capture components
from capture.ocr_processor import OCRProcessor

# System integration components  
from system.system_tray import SystemTrayManager
from system.notification_manager import NotificationManager
from system.permission_handler import PermissionHandler

# Utilities
from utils.logging_config import setup_logging


class HorizonApp:
    """Main application class - Python equivalent of AppDelegate in Swift"""
    
    def __init__(self):
        # Core managers
        self.context_manager = AIContextManager()
        self.auth_manager = AuthManager()
        self.transcription_service = TranscriptionService()  # NEW: Voice transcription service
        # REMOVED: self.overlay_manager = OverlayManager() - Overlays now handled by frontend
        
        # AI and WebSocket managers
        self.ai_connection_manager = AIConnectionManager()
        self.tag_websocket_manager = TagWebSocketManager()
        self.auto_context_manager = AutoContextManager()
        
        # Essential capture components only
        self.ocr_processor = OCRProcessor()
        
        # System integration components
        self.system_tray = SystemTrayManager()
        self.notification_manager = NotificationManager()
        self.permission_handler = PermissionHandler()
        
        # Application state
        self.is_initialized = False
        
    async def startup(self):
        """Initialize all managers - equivalent to applicationDidFinishLaunching"""
        try:
            # Setup logging
            setup_logging()
            print("🚀 Starting Horizon AI Assistant Backend...")
            
            # Phase 1: Check and setup system permissions (excluding input device permissions)
            print("📋 Checking system permissions...")
            await self.permission_handler.check_all_permissions()
            
            # Show permission report
            self.permission_handler.print_permission_report()
            
            # Setup required permissions
            success, failed = await self.permission_handler.setup_required_permissions()
            if not success:
                print(f"⚠️  Warning: Some required permissions are missing: {failed}")
                print("Some features may not work properly. Run with --setup-permissions to fix.")
            
            # Phase 2: Initialize core services
            print("🔧 Initializing core services...")
            
            # Initialize AuthManager first
            await self.auth_manager.initialize()
            
            # Initialize Transcription Service
            print("🎙️ Loading voice transcription service...")
            # Transcription service initializes Whisper automatically
            
            # Initialize AI Connection Manager
            self.ai_connection_manager.set_message_callback(self._on_ai_message_received)
            self.ai_connection_manager.set_connection_callback(self._on_ai_connection_changed)
            await self.ai_connection_manager.connect()
            
            # Initialize Tag WebSocket Manager if authenticated
            if self.auth_manager.is_authenticated:
                tenant_name = self.auth_manager.get_tenant_name()
                await self.tag_websocket_manager.initialize(tenant_name)
            
            # Phase 3: Initialize system integration
            print("🖥️  Setting up system integration...")
            
            # Setup notification manager
            await self.notification_manager.setup()
            
            # Setup system tray
            tray_success = await self.system_tray.setup()
            if tray_success:
                self._register_tray_callbacks()
            
            # REMOVED: Overlay manager setup - Overlays now handled by frontend
            
            # Phase 4: Setup Auto Context Manager callbacks
            print("🔍 Setting up context management...")
            self.auto_context_manager.set_notes_callback(self._on_context_notes_updated)
            self.auto_context_manager.set_loading_callback(self._on_context_loading_changed)
            self.auto_context_manager.set_error_callback(self._on_context_error)
            
            # Phase 5: Send startup notification
            await self.notification_manager.send_startup_notification()
            
            self.is_initialized = True
            print("✅ Horizon AI Assistant Backend started successfully!")
            
            # Show system status
            await self._print_system_status()
            
        except Exception as e:
            print(f"❌ Failed to start Horizon AI Assistant: {e}")
            await self.notification_manager.send_error_notification(
                "Startup Error", 
                f"Failed to start Horizon AI Assistant: {str(e)}"
            )
            raise
    
    async def _print_system_status(self):
        """Print comprehensive system status."""
        print("\n" + "="*60)
        print("🌟 HORIZON AI ASSISTANT - SYSTEM STATUS")
        print("="*60)
        
        # Core services
        print(f"🔐 Authentication: {'✅ Active' if self.auth_manager.is_authenticated else '❌ Inactive'}")
        print(f"🤖 AI Connection: {'✅ Connected' if self.ai_connection_manager.is_connected else '❌ Disconnected'}")
        print(f"🏷️  Tag Manager: {'✅ Connected' if self.tag_websocket_manager.is_connected else '❌ Disconnected'}")
        
        # System integration
        print(f"🔔 Notifications: {'✅ Enabled' if self.notification_manager.is_enabled() else '❌ Disabled'}")
        print(f"📊 System Tray: {'✅ Active' if self.system_tray.is_active else '❌ Inactive'}")
        
        # Input and capture
        print(f"⌨️  Hotkeys: {'✅ Frontend Managed' if True else '❌ Not Available'}")
        print(f"🎯 Overlays: {'✅ Frontend Managed' if True else '❌ Not Available'}")
        print(f"👁️  OCR Processor: {'✅ Ready' if hasattr(self.ocr_processor, 'thread_pool') else '❌ Not Ready'}")
        
        # Show available endpoints
        print(f"\n🌐 API Server: http://127.0.0.1:8000")
        print(f"📡 WebSocket: ws://127.0.0.1:8000/ws")
        print(f"📖 API Docs: http://127.0.0.1:8000/docs")
        
        print("="*60 + "\n")
    
    def _register_tray_callbacks(self):
        """Register system tray callbacks."""
        self.system_tray.register_callback('menu_item_clicked', self._on_tray_menu_item_clicked)
        self.system_tray.register_callback('settings_clicked', self._on_tray_settings_clicked)
        self.system_tray.register_callback('quit_clicked', self._on_tray_quit_clicked)
    
    async def shutdown(self):
        """Cleanup resources - equivalent to applicationWillTerminate"""
        print("🛑 Shutting down Horizon AI Assistant...")
        
        try:
            # Disconnect AI services
            await self.ai_connection_manager.disconnect()
            await self.tag_websocket_manager.disconnect()
            await self.auto_context_manager.disconnect()
            
            # Cleanup system integration
            await self.system_tray.cleanup()
            await self.notification_manager.cleanup()
            
            # REMOVED: Overlay manager cleanup - No longer needed
            
            print("✅ Horizon AI Assistant shutdown complete")
            
        except Exception as e:
            print(f"⚠️  Error during shutdown: {e}")
    
    # REMOVED: All overlay-related callback methods - Overlays now handled by frontend
    
    # AI callback methods
    def _on_ai_message_received(self, message: str):
        """Handle AI message updates"""
        try:
            # Send notification for AI response
            asyncio.create_task(
                self.notification_manager.send_ai_response_notification(message)
            )
            
            print(f"🤖 AI Message: {message[:100]}...")
            
        except Exception as e:
            print(f"Error handling AI message: {e}")
    
    def _on_ai_connection_changed(self, connected: bool):
        """Handle AI connection state changes"""
        status = "Connected" if connected else "Disconnected"
        print(f"🔗 AI Connection: {status}")
    
    # Context callback methods
    def _on_context_notes_updated(self, notes):
        """Handle context notes updates"""
        try:
            count = len(notes) if notes else 0
            print(f"📝 Context notes updated: {count} notes found")
            
            # Send notification
            asyncio.create_task(
                self.notification_manager.send_context_update_notification("notes", count)
            )
            
        except Exception as e:
            print(f"Error handling context notes update: {e}")
    
    def _on_context_loading_changed(self, loading: bool):
        """Handle context loading state changes"""
        status = "Loading..." if loading else "Complete"
        print(f"🔍 Context search: {status}")
    
    def _on_context_error(self, error: Exception):
        """Handle context search errors"""
        print(f"❌ Context search error: {error}")
        asyncio.create_task(
            self.notification_manager.send_error_notification(
                "Context Search Error", 
                str(error)
            )
        )
    
    # System tray callback methods (now only show notifications, no direct overlay control)
    async def _on_tray_menu_item_clicked(self, action: str):
        """Handle system tray menu item clicks."""
        try:
            if action == "toggle_ai_assist":
                await self.notification_manager.send_quick_notification(
                    "AI Assist", 
                    "Use global hotkey or frontend interface to toggle overlays"
                )
            elif action == "toggle_auto_context":
                await self.notification_manager.send_quick_notification(
                    "Auto Context", 
                    "Use global hotkey or frontend interface to toggle overlays"
                )
            elif action == "toggle_quick_capture":
                await self.notification_manager.send_quick_notification(
                    "Quick Capture", 
                    "Use global hotkey or frontend interface to toggle overlays"
                )
            elif action == "show_about":
                await self.notification_manager.send_quick_notification(
                    "About Horizon AI Assistant",
                    "AI-powered desktop overlay assistant for enhanced productivity"
                )
        except Exception as e:
            print(f"Tray menu action error: {e}")
    
    def _on_tray_settings_clicked(self):
        """Handle system tray settings click."""
        print("🔧 Opening settings... (Handled by frontend)")
    
    def _on_tray_quit_clicked(self):
        """Handle system tray quit click."""
        print("👋 Quit requested from system tray")
        # This would typically trigger application shutdown
    
    async def send_ai_message(self, text: str, smarter_analysis: bool = False):
        """Send message to AI service with current context"""
        try:
            # Capture current context (without screenshot - frontend provides images)
            context_data = await self.context_manager.capture_current_context(capture_image=False)
            
            # Send to AI with context (image data will come from frontend)
            await self.ai_connection_manager.send_message(
                text=text,
                ocr_text=context_data.ocr_text,
                selected_text=context_data.selected_text,
                browser_url=context_data.browser_url,
                image_data=None,  # Frontend will provide via separate API
                smarter_analysis_enabled=smarter_analysis
            )
            
        except Exception as e:
            print(f"Error sending AI message: {e}")
            raise


# Create global app instance
horizon_app = HorizonApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    await horizon_app.startup()
    yield
    # Shutdown
    await horizon_app.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Horizon AI Assistant API",
    description="Backend API for Horizon AI Assistant Desktop Application",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for PyQt6 frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication with PyQt6 frontend"""
    await websocket.accept()
    
    # REMOVED: overlay manager websocket registration - Overlays now handled by frontend
    
    try:
        while True:
            data = await websocket.receive_text()
            # Handle WebSocket messages from PyQt6 frontend
            import json
            try:
                message = json.loads(data)
                await handle_websocket_message(websocket, message)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "error": "Invalid JSON format"
                }))
    except WebSocketDisconnect:
        # REMOVED: overlay manager websocket cleanup - No longer needed
        print("WebSocket disconnected")


async def handle_websocket_message(websocket: WebSocket, message: dict):
    """Handle incoming WebSocket messages from PyQt6 frontend"""
    import json
    
    message_type = message.get("type")
    
    if message_type == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
    
    elif message_type == "get_context":
        # Request for current context
        context_data = await horizon_app.context_manager.capture_current_context()
        await websocket.send_text(json.dumps({
            "type": "context_data",
            "data": {
                "selected_text": context_data.selected_text,
                "ocr_text": context_data.ocr_text,
                "browser_url": context_data.browser_url,
                "timestamp": context_data.timestamp.isoformat()
            }
        }))
    
    # REMOVED: overlay_action handling - Overlays now handled by frontend
    # Frontend manages overlays directly, no need for backend coordination
    
    elif message_type == "ai_message":
        # Real-time AI chat message with streaming support
        text = message.get("text", "")
        smarter_analysis = message.get("smarter_analysis", False)
        context_data = message.get("context", {})
        
        if text:
            try:
                # Set up real-time streaming callbacks
                def on_ai_chunk(chunk: str):
                    """Callback for AI response chunks"""
                    asyncio.create_task(websocket.send_text(json.dumps({
                        "type": "ai_chunk",
                        "data": {
                            "chunk": chunk,
                            "is_complete": False
                        }
                    })))
                
                def on_ai_complete(full_response: str):
                    """Callback for AI response completion"""
                    asyncio.create_task(websocket.send_text(json.dumps({
                        "type": "ai_response_complete",
                        "data": {
                            "content": full_response,
                            "is_complete": True
                        }
                    })))
                
                def on_ai_thinking(thinking: bool):
                    """Callback for AI thinking status"""
                    asyncio.create_task(websocket.send_text(json.dumps({
                        "type": "ai_thinking",
                        "data": {"thinking": thinking}
                    })))
                
                # Set streaming callbacks on AI manager
                horizon_app.ai_connection_manager.set_streaming_callbacks(
                    on_chunk=on_ai_chunk,
                    on_complete=on_ai_complete,
                    on_thinking=on_ai_thinking
                )
                
                # Send thinking status immediately
                await websocket.send_text(json.dumps({
                    "type": "ai_thinking",
                    "data": {"thinking": True}
                }))
                
                # Capture enhanced context including frontend-provided data
                backend_context = await horizon_app.context_manager.capture_current_context(capture_image=False)
                
                # Merge frontend context with backend context
                merged_context = {
                    "ocr_text": context_data.get("ocr_text", backend_context.ocr_text),
                    "selected_text": context_data.get("selected_text", backend_context.selected_text),
                    "browser_url": context_data.get("browser_url", backend_context.browser_url),
                    "window_title": context_data.get("window_title", ""),
                    "app_name": context_data.get("app_name", "")
                }
                
                # Send to AI with streaming enabled
                await horizon_app.ai_connection_manager.send_message_streaming(
                    text=text,
                    ocr_text=merged_context["ocr_text"],
                    selected_text=merged_context["selected_text"],
                    browser_url=merged_context["browser_url"],
                    smarter_analysis_enabled=smarter_analysis
                )
                
                # Confirm message sent
                await websocket.send_text(json.dumps({
                    "type": "ai_message_sent",
                    "status": "success"
                }))
                
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "ai_error",
                    "data": {
                        "error": str(e),
                        "message": "Failed to process AI message"
                    }
                }))
    
    elif message_type == "ai_stop_generation":
        # Stop AI response generation
        try:
            horizon_app.ai_connection_manager.stop_generation()
            await websocket.send_text(json.dumps({
                "type": "ai_generation_stopped",
                "status": "success"
            }))
        except Exception as e:
            await websocket.send_text(json.dumps({
                "type": "ai_error",
                "data": {"error": str(e)}
            }))

    elif message_type == "search_context":
        # Search for context notes
        ocr_text = message.get("ocr_text", "")
        
        if ocr_text:
            if not horizon_app.auto_context_manager.context_search_api.is_connected:
                await horizon_app.auto_context_manager.connect()
            
            await horizon_app.auto_context_manager.search_context(ocr_text)
            await websocket.send_text(json.dumps({
                "type": "context_search_started",
                "status": "success"
            }))


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "Horizon AI Assistant Backend is running",
        "components": {
            "ai_connected": horizon_app.ai_connection_manager.is_connected,
            "auth_status": horizon_app.auth_manager.is_authenticated,
            "tag_manager_connected": horizon_app.tag_websocket_manager.is_connected,
            "context_search_connected": horizon_app.auto_context_manager.context_search_api.is_connected
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )