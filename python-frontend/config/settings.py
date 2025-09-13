"""
Settings management for Horizon Overlay
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class APIProvider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    AZURE = "azure"


@dataclass
class HotkeyConfig:
    """Hotkey configuration"""
    ai_assist: str = "ctrl+space"
    quick_capture: str = "ctrl+shift+space"
    auto_context: str = "ctrl+alt+space"
    toggle_settings: str = "ctrl+comma"


@dataclass
class WindowConfig:
    """Window positioning and behavior configuration"""
    ai_assist_width: int = 480
    ai_assist_height: int = 400
    quick_capture_width: int = 721
    quick_capture_height: int = 80
    auto_context_width: int = 400
    auto_context_height: int = 500
    auto_focus: bool = True
    stay_on_top: bool = True


@dataclass
class BackendConfig:
    """Backend service configuration"""
    base_url: str = "http://http://127.0.0.1:8000"
    websocket_url: str = "ws://http://127.0.0.1:8000/ws"
    api_timeout: int = 30
    reconnect_attempts: int = 3


@dataclass
class AudioConfig:
    """Audio input configuration"""
    enabled: bool = False
    device_id: Optional[int] = None
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024


@dataclass
class VoiceConfig:
    """Voice processing configuration"""
    enabled: bool = True
    auto_show_ai_assist: bool = True
    system_audio_monitoring: bool = True
    voice_activity_threshold: float = 0.02
    min_voice_duration: float = 1.0
    silence_duration: float = 2.0


@dataclass
class UIConfig:
    """UI behavior configuration"""
    auto_show_context: bool = True
    auto_open_ai_with_context: bool = False
    remember_window_positions: bool = True
    fade_animations: bool = True


class Settings:
    """Main settings manager"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "horizon-overlay"
        self.config_file = self.config_dir / "settings.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup completion flag
        self.is_setup_complete = False
        
        # Default settings
        self.theme = Theme.AUTO
        self.api_provider = APIProvider.OPENAI
        self.hotkeys = HotkeyConfig()
        self.windows = WindowConfig()
        self.backend = BackendConfig()
        self.audio = AudioConfig()
        self.voice = VoiceConfig()
        self.ui = UIConfig()
        
        # API Keys (stored separately for security)
        self.api_keys: Dict[str, str] = {}
        
        # Load existing settings
        self.load()
    
    def load(self):
        """Load settings from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                
                # Load setup completion flag
                if 'is_setup_complete' in data:
                    self.is_setup_complete = data['is_setup_complete']
                
                # Load theme
                if 'theme' in data:
                    self.theme = Theme(data['theme'])
                
                # Load API provider
                if 'api_provider' in data:
                    self.api_provider = APIProvider(data['api_provider'])
                
                # Load hotkeys
                if 'hotkeys' in data:
                    hotkey_data = data['hotkeys']
                    self.hotkeys = HotkeyConfig(**hotkey_data)
                
                # Load window config
                if 'windows' in data:
                    window_data = data['windows']
                    self.windows = WindowConfig(**window_data)
                
                # Load backend config
                if 'backend' in data:
                    backend_data = data['backend']
                    self.backend = BackendConfig(**backend_data)
                
                # Load audio config
                if 'audio' in data:
                    audio_data = data['audio']
                    self.audio = AudioConfig(**audio_data)
                
                # Load voice config
                if 'voice' in data:
                    voice_data = data['voice']
                    self.voice = VoiceConfig(**voice_data)
                
                # Load UI config
                if 'ui' in data:
                    ui_data = data['ui']
                    self.ui = UIConfig(**ui_data)
                
                # Load API keys
                if 'api_keys' in data:
                    self.api_keys = data['api_keys']
                
            except Exception as e:
                print(f"Error loading settings: {e}")
                print("Using default settings")
    
    def save(self):
        """Save settings to file"""
        try:
            data = {
                'is_setup_complete': self.is_setup_complete,
                'theme': self.theme.value,
                'api_provider': self.api_provider.value,
                'hotkeys': asdict(self.hotkeys),
                'windows': asdict(self.windows),
                'backend': asdict(self.backend),
                'audio': asdict(self.audio),
                'voice': asdict(self.voice),
                'ui': asdict(self.ui),
                'api_keys': self.api_keys
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get_api_key(self, provider: Optional[APIProvider] = None) -> Optional[str]:
        """Get API key for specified provider (or current provider)"""
        provider = provider or self.api_provider
        return self.api_keys.get(provider.value)
    
    def set_api_key(self, provider: APIProvider, key: str):
        """Set API key for provider"""
        self.api_keys[provider.value] = key
        self.save()
    
    def mark_setup_complete(self):
        """Mark setup as complete"""
        self.is_setup_complete = True
        self.save()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary"""
        return {
            'theme': self.theme.value,
            'api_provider': self.api_provider.value,
            'hotkeys': asdict(self.hotkeys),
            'windows': asdict(self.windows),
            'backend': asdict(self.backend),
            'audio': asdict(self.audio),
            'voice': asdict(self.voice),
            'ui': asdict(self.ui)
        }