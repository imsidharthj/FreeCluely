"""
Main Overlay Manager - Coordinates all overlay windows
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Set, List
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

from ui.windows.ai_assist_window import AIAssistWindow
from ui.windows.quick_capture_window import QuickCaptureWindow
from ui.windows.auto_context_window import AutoContextWindow
from config.settings import Settings
from services.backend_client import BackendClient
from services.shortcut_manager import ShortcutManager
from utils.voice_input import VoiceInputManager, AudioConfig


class OverlayManager(QObject):
    """Main overlay manager - coordinates all overlay windows"""
    
    # Signals
    overlay_shown = pyqtSignal(str)  # overlay_type
    overlay_hidden = pyqtSignal(str)  # overlay_type
    context_changed = pyqtSignal(dict)  # context_data
    voice_detected = pyqtSignal()
    voice_transcribed = pyqtSignal(str)  # transcribed text
    
    def __init__(self, settings: Settings, backend_client: Optional[BackendClient] = None):
        super().__init__()
        self.settings = settings
        self.backend_client = backend_client
        self.logger = logging.getLogger(__name__)
        
        # Window instances
        self.ai_assist_window: Optional[AIAssistWindow] = None
        self.quick_capture_window: Optional[QuickCaptureWindow] = None
        self.auto_context_window: Optional[AutoContextWindow] = None
        
        # State
        self.active_overlays: Set[str] = set()
        self.current_context: Dict[str, Any] = {}
        self.selected_text: str = ""
        
        # Services
        self.shortcut_manager: Optional[ShortcutManager] = None
        
        # Voice input manager for continuous monitoring
        self.voice_manager: Optional[VoiceInputManager] = None
        self.system_audio_manager: Optional[VoiceInputManager] = None
        self.voice_monitoring_enabled = False
        
        # Initialize
        self._setup_shortcuts()
        self._setup_voice_monitoring()
        self._connect_backend()
        
        # Context monitoring timer
        self.context_timer = QTimer()
        self.context_timer.timeout.connect(self._monitor_context_sync)
        self.context_timer.start(2000)  # Check every 2 seconds
    
    def _setup_shortcuts(self):
        """Setup global shortcuts for overlays"""
        try:
            self.shortcut_manager = ShortcutManager(self.settings)
            
            # Register shortcuts
            self.shortcut_manager.register_shortcut(
                "ai_assist", 
                self.settings.hotkeys.ai_assist,
                self.toggle_ai_assist
            )
            
            self.shortcut_manager.register_shortcut(
                "quick_capture",
                self.settings.hotkeys.quick_capture,
                self.toggle_quick_capture
            )
            
            self.shortcut_manager.register_shortcut(
                "auto_context",
                self.settings.hotkeys.auto_context,
                self.toggle_auto_context
            )
            
            self.logger.info("Global shortcuts registered successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup shortcuts: {e}")
    
    def _setup_voice_monitoring(self):
        """Setup voice input monitoring for both microphone and system audio"""
        try:
            if not self.backend_client:
                self.logger.warning("No backend client - voice monitoring disabled")
                return
                
            # Create audio configuration
            audio_config = AudioConfig(
                sample_rate=16000,
                channels=1,
                chunk_size=1024,
                device_id=None  # Use default device
            )
            
            # Setup microphone monitoring
            self.voice_manager = VoiceInputManager(audio_config, capture_system_audio=False)
            self.voice_manager.set_backend_client(self.backend_client)
            self.voice_manager.configure_voice_to_ai(auto_send=True)
            
            # Setup system audio monitoring (for meeting transcription)
            self.system_audio_manager = VoiceInputManager(audio_config, capture_system_audio=True)
            self.system_audio_manager.set_backend_client(self.backend_client)
            self.system_audio_manager.configure_voice_to_ai(auto_send=False)  # Process manually
            
            # Configure callbacks
            self.voice_manager.set_callbacks(
                on_voice_detected=self._on_voice_detected,
                on_transcription_ready=self._on_voice_transcribed
            )
            
            self.system_audio_manager.set_callbacks(
                on_voice_detected=self._on_system_audio_detected,
                on_transcription_ready=self._on_system_audio_transcribed
            )
            
            # Configure VAD for better meeting detection
            self.voice_manager.configure_vad(
                silence_threshold=0.02,
                min_voice_duration=1.0,
                silence_duration=2.0
            )
            
            self.system_audio_manager.configure_vad(
                silence_threshold=0.01,
                min_voice_duration=2.0,  # Longer for system audio
                silence_duration=3.0
            )
            
            self.logger.info("Voice monitoring setup complete")
            
        except Exception as e:
            self.logger.error(f"Failed to setup voice monitoring: {e}")
    
    async def start_voice_monitoring(self):
        """Start continuous voice monitoring for meeting detection"""
        if not self.voice_manager or not self.system_audio_manager:
            self.logger.warning("Voice managers not initialized")
            return False
            
        try:
            # Start microphone monitoring
            mic_started = await self.voice_manager.start_recording()
            
            # Start system audio monitoring for meeting transcription
            system_started = await self.system_audio_manager.start_recording()
            
            if mic_started or system_started:
                self.voice_monitoring_enabled = True
                self.logger.info("Voice monitoring started")
                return True
            else:
                self.logger.error("Failed to start voice monitoring")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting voice monitoring: {e}")
            return False
    
    async def stop_voice_monitoring(self):
        """Stop voice monitoring"""
        if self.voice_manager:
            await self.voice_manager.stop_recording()
        if self.system_audio_manager:
            await self.system_audio_manager.stop_recording()
        self.voice_monitoring_enabled = False
        self.logger.info("Voice monitoring stopped")
    
    def _on_voice_detected(self):
        """Handle user voice detection"""
        self.voice_detected.emit()
        self.logger.debug("User voice detected")
    
    def _on_system_audio_detected(self):
        """Handle system audio detection (meeting participants)"""
        self.logger.debug("System audio detected (meeting)")
    
    def _on_voice_transcribed(self, transcription):
        """Handle user voice transcription"""
        if transcription.success and transcription.text.strip():
            self.voice_transcribed.emit(transcription.text)
            self.logger.info(f"User voice transcribed: {transcription.text[:50]}...")
            
            # Auto-show AI assist for voice queries
            if self.settings.voice.auto_show_ai_assist:
                if not self.is_overlay_active("ai_assist"):
                    self.show_ai_assist()
    
    def _on_system_audio_transcribed(self, transcription):
        """Handle system audio transcription (meeting content)"""
        if transcription.success and transcription.text.strip():
            self.logger.info(f"Meeting audio transcribed: {transcription.text[:50]}...")
            
            # Store meeting context for AI assistance
            self.current_context['meeting_audio'] = transcription.text
            
            # Auto-refresh context window with meeting content
            if self.auto_context_window and "auto_context" in self.active_overlays:
                # Update context with meeting information
                asyncio.create_task(self._update_meeting_context(transcription.text))
    
    async def _update_meeting_context(self, meeting_text: str):
        """Update context with meeting information"""
        try:
            # Send meeting transcript to backend for context analysis
            if self.backend_client:
                response = await self.backend_client.send_meeting_context(meeting_text)
                if response.success:
                    self.logger.debug("Meeting context updated")
        except Exception as e:
            self.logger.error(f"Failed to update meeting context: {e}")
    
    def _connect_backend(self):
        """Connect to backend for real-time updates"""
        if self.backend_client:
            self.backend_client.register_message_handler('context_changed', self._on_context_changed)
            self.backend_client.register_message_handler('selected_text', self._on_selected_text_changed)
            self.backend_client.register_message_handler('window_focus', self._on_window_focus_changed)
    
    def _monitor_context_sync(self):
        """Monitor system context periodically (sync version)"""
        if self.backend_client and self.active_overlays:
            # Only try async operations if we have a running event loop
            try:
                loop = asyncio.get_running_loop()
                if loop and not loop.is_closed():
                    # Schedule the async update
                    asyncio.create_task(self._update_context())
                else:
                    self.logger.debug("No running event loop for context update")
            except RuntimeError:
                # No running event loop, skip this update
                self.logger.debug("No running event loop, skipping context update")
            except Exception as e:
                self.logger.debug(f"Context monitoring error: {e}")
    
    async def _update_context(self):
        """Update current context from system"""
        try:
            response = await self.backend_client.get_current_context()
            if response.success:
                new_context = response.data
                if new_context != self.current_context:
                    self.current_context = new_context
                    self.context_changed.emit(new_context)
                    self._propagate_context_updates()
        except Exception as e:
            self.logger.debug(f"Context update failed: {e}")
    
    def _propagate_context_updates(self):
        """Propagate context updates to active overlays"""
        # Update AI Assist with selected text
        if self.ai_assist_window and "ai_assist" in self.active_overlays:
            selected_text = self.current_context.get('selected_text', '')
            if selected_text != self.selected_text:
                self.selected_text = selected_text
                self.ai_assist_window.update_selected_text(selected_text)
        
        # Update Auto Context if it's visible
        if self.auto_context_window and "auto_context" in self.active_overlays:
            # Auto context will refresh itself based on context changes
            pass
    
    # AI Assist Window Management
    def show_ai_assist(self, selected_text: str = ""):
        """Show AI Assist window"""
        if not self.ai_assist_window:
            self.ai_assist_window = AIAssistWindow(self.settings, self.backend_client)
            self.ai_assist_window.window_closed.connect(lambda: self._on_overlay_closed("ai_assist"))
            self.ai_assist_window.message_sent.connect(self._on_ai_message_sent)
        
        if selected_text:
            self.ai_assist_window.update_selected_text(selected_text)
        
        self.ai_assist_window.show()
        self.active_overlays.add("ai_assist")
        self.overlay_shown.emit("ai_assist")
        self.logger.info("AI Assist window shown")
    
    def hide_ai_assist(self):
        """Hide AI Assist window"""
        if self.ai_assist_window:
            self.ai_assist_window.hide()
            self.active_overlays.discard("ai_assist")
            self.overlay_hidden.emit("ai_assist")
    
    def toggle_ai_assist(self):
        """Toggle AI Assist window"""
        if "ai_assist" in self.active_overlays:
            self.hide_ai_assist()
        else:
            selected_text = self.current_context.get('selected_text', '')
            self.show_ai_assist(selected_text)
    
    # Quick Capture Window Management
    def show_quick_capture(self):
        """Show Quick Capture window"""
        if not self.quick_capture_window:
            self.quick_capture_window = QuickCaptureWindow(self.settings, self.backend_client)
            self.quick_capture_window.window_closed.connect(lambda: self._on_overlay_closed("quick_capture"))
            self.quick_capture_window.capture_saved.connect(self._on_capture_saved)
        
        self.quick_capture_window.show()
        self.active_overlays.add("quick_capture")
        self.overlay_shown.emit("quick_capture")
        self.logger.info("Quick Capture window shown")
    
    def hide_quick_capture(self):
        """Hide Quick Capture window"""
        if self.quick_capture_window:
            self.quick_capture_window.hide()
            self.active_overlays.discard("quick_capture")
            self.overlay_hidden.emit("quick_capture")
    
    def toggle_quick_capture(self):
        """Toggle Quick Capture window"""
        if "quick_capture" in self.active_overlays:
            self.hide_quick_capture()
        else:
            self.show_quick_capture()
    
    # Auto Context Window Management
    def show_auto_context(self):
        """Show Auto Context window"""
        if not self.auto_context_window:
            self.auto_context_window = AutoContextWindow(self.settings, self.backend_client)
            self.auto_context_window.window_closed.connect(lambda: self._on_overlay_closed("auto_context"))
            self.auto_context_window.context_selected.connect(self._on_context_selected)
            self.auto_context_window.search_requested.connect(self._on_context_search)
        
        self.auto_context_window.show()
        self.active_overlays.add("auto_context")
        self.overlay_shown.emit("auto_context")
        self.logger.info("Auto Context window shown")
    
    def hide_auto_context(self):
        """Hide Auto Context window"""
        if self.auto_context_window:
            self.auto_context_window.hide()
            self.active_overlays.discard("auto_context")
            self.overlay_hidden.emit("auto_context")
    
    def toggle_auto_context(self):
        """Toggle Auto Context window"""
        if "auto_context" in self.active_overlays:
            self.hide_auto_context()
        else:
            self.show_auto_context()
    
    # Utility Methods
    def hide_all_overlays(self):
        """Hide all overlay windows"""
        self.hide_ai_assist()
        self.hide_quick_capture()
        self.hide_auto_context()
    
    def get_active_overlays(self) -> Set[str]:
        """Get set of currently active overlay types"""
        return self.active_overlays.copy()
    
    def is_overlay_active(self, overlay_type: str) -> bool:
        """Check if an overlay is currently active"""
        return overlay_type in self.active_overlays
    
    # Event Handlers
    def _on_overlay_closed(self, overlay_type: str):
        """Handle overlay window close"""
        self.active_overlays.discard(overlay_type)
        self.overlay_hidden.emit(overlay_type)
        self.logger.debug(f"{overlay_type} overlay closed")
    
    def _on_ai_message_sent(self, message: str):
        """Handle AI message sent"""
        self.logger.debug(f"AI message sent: {message[:50]}...")
        
        # Optionally show context window if AI conversation starts
        if self.settings.ui.auto_show_context and not self.is_overlay_active("auto_context"):
            self.show_auto_context()
    
    def _on_capture_saved(self, capture_text: str):
        """Handle capture saved"""
        self.logger.info(f"Capture saved: {len(capture_text)} characters")
        
        # Optionally refresh context after capture
        if self.auto_context_window and "auto_context" in self.active_overlays:
            self.auto_context_window._refresh_context()
    
    def _on_context_selected(self, context_data: Dict[str, Any]):
        """Handle context item selection"""
        self.logger.debug(f"Context selected: {context_data.get('title', 'Unknown')}")
        
        # Optionally open AI Assist with context
        if self.settings.ui.auto_open_ai_with_context:
            if not self.is_overlay_active("ai_assist"):
                self.show_ai_assist()
            
            # Set the context in AI Assist
            if self.ai_assist_window:
                content = context_data.get('content', '')
                if content:
                    self.ai_assist_window.update_selected_text(content[:500] + "..." if len(content) > 500 else content)
    
    def _on_context_search(self, query: str):
        """Handle context search request"""
        self.logger.debug(f"Context search: {query}")
    
    # Backend Event Handlers
    def _on_context_changed(self, data: Dict[str, Any]):
        """Handle context change from backend"""
        self.current_context.update(data)
        self.context_changed.emit(self.current_context)
        self._propagate_context_updates()
    
    def _on_selected_text_changed(self, data: Dict[str, Any]):
        """Handle selected text change"""
        selected_text = data.get('text', '')
        if selected_text != self.selected_text:
            self.selected_text = selected_text
            self.current_context['selected_text'] = selected_text
            
            # Update AI Assist if active
            if self.ai_assist_window and "ai_assist" in self.active_overlays:
                self.ai_assist_window.update_selected_text(selected_text)
    
    def _on_window_focus_changed(self, data: Dict[str, Any]):
        """Handle window focus changes"""
        window_title = data.get('window_title', '')
        app_name = data.get('app_name', '')
        
        self.current_context.update({
            'active_window': window_title,
            'active_app': app_name
        })
        
        self.logger.debug(f"Window focus changed: {app_name} - {window_title}")
    
    def cleanup(self):
        """Cleanup resources"""
        self.context_timer.stop()
        
        if self.shortcut_manager:
            self.shortcut_manager.cleanup()
        
        self.hide_all_overlays()
        
        # Clean up window instances
        if self.ai_assist_window:
            self.ai_assist_window.deleteLater()
            self.ai_assist_window = None
        
        if self.quick_capture_window:
            self.quick_capture_window.deleteLater()
            self.quick_capture_window = None
        
        if self.auto_context_window:
            self.auto_context_window.deleteLater()
            self.auto_context_window = None
        
        # Stop voice monitoring
        asyncio.create_task(self.stop_voice_monitoring())
        
        self.logger.info("Overlay manager cleaned up")