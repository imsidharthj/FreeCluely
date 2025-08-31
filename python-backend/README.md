# Horizon AI Assistant - Python Backend

Python FastAPI backend for the Horizon AI Assistant, converted from Swift macOS application to support Ubuntu/Wayland.

## Overview

This backend provides REST API and WebSocket services for the Horizon AI Assistant frontend. The backend handles AI communication, context processing (OCR), authentication, and system integration while the frontend handles all GUI operations including overlay management, hotkey detection, theme management, and user interface.

## Architecture Changes

### 🎯 **Frontend-Centric Design (Updated)**

**Backend Responsibilities** (Core Logic Only):
- **AI Communication**: OpenAI API integration and message processing
- **Context Processing**: OCR text extraction and context analysis  
- **Authentication**: User authentication and session management
- **System Integration**: Notifications, system tray (Linux), background services

**Frontend Responsibilities** (All GUI Operations):
- **Overlay Management**: All overlay windows, state management, positioning
- **Hotkey Detection**: Platform-specific global hotkey handling
- **Theme Management**: UI themes, styling, visual preferences
- **Screenshot Capture**: Screen capture using PyQt6/pyscreenshot
- **User Interface**: All interactive elements and GUI logic

### **Communication Flow**:
```
Frontend → API/WebSocket → Backend Processing → API Response → Frontend Display
```

## Core Components

```
python-backend/
├── main.py                 # FastAPI server entry point
├── requirements.txt        # Python dependencies
├── setup.sh               # Ubuntu setup script
│
├── services/              # Core business logic (GUI-free)
│   ├── context_manager.py # OCR processing, context analysis
│   └── auth_manager.py    # Authentication management
│
├── ai/                    # AI integration
│   ├── connection_manager.py # OpenAI API communication
│   └── tag_websocket_manager.py # Tag management
│
├── api/                   # FastAPI routes
│   ├── routes.py          # REST API endpoints
│   └── context_search.py  # Context search API
│
├── capture/               # Processing components
│   └── ocr_processor.py   # OCR text extraction (Tesseract)
│
├── input/                 # Voice input only
│   ├── voice_input_manager.py # Voice processing
│   └── shortcut_config.py    # Configuration models
│
├── models/                # Data models
│   ├── context_data.py    # Context and note models
│   └── shortcut.py        # Keyboard shortcut model
│
├── settings/              # Backend configuration (GUI-free)
│   ├── settings_manager.py   # Core settings persistence
│   ├── user_preferences.py   # User preference models
│   └── config_validator.py   # Configuration validation
│
├── system/                # System integration
│   ├── notification_manager.py # Desktop notifications
│   ├── permission_handler.py   # System permissions
│   └── system_tray.py          # System tray integration
│
└── utils/                 # Utilities
    └── logging_config.py  # Logging configuration
```

## Key Features

### 1. Screenshot Processing (Frontend-to-Backend)
- **Frontend**: Captures screenshots using PyQt6/pyscreenshot
- **Backend**: Processes received images with OCR via API
- **Flow**: `Frontend Capture → Base64 → Backend API → OCR → Response`

### 2. Context Processing
- **Backend**: OCR text extraction from frontend screenshots
- **Backend**: Selected text via API (clipboard handled by frontend)
- **Backend**: Browser URL detection from window titles
- **Backend**: Context aggregation and AI integration

### 3. AI Communication
- **Backend**: OpenAI API integration and message processing
- **Backend**: Context-aware AI responses
- **Frontend**: Chat interface and user interaction

## API Endpoints

### Health Check
```
GET / - Health check with component status
GET /api/v1/health - Detailed health status
```

### Context Management
```
POST /api/v1/context/capture - Capture current context (no screenshot)
POST /api/v1/context/process-screenshot - Process screenshot from frontend
POST /api/v1/context/search - Search context based on OCR text
GET /api/v1/context/notes - Get current context notes
POST /api/v1/screenshot/process - Alternative screenshot processing
```

### AI Communication
```
POST /api/v1/ai/send-message - Send message to AI with context
GET /api/v1/ai/messages - Get AI conversation history
GET /api/v1/ai/status - Get AI connection status
POST /api/v1/ai/clear-conversation - Clear conversation history
```

### Authentication
```
POST /api/v1/auth/login - Authenticate user
POST /api/v1/auth/logout - Logout user
GET /api/v1/auth/status - Get auth status
```

### System Status
```
GET /api/v1/system/status - Get comprehensive system status
```

### Tag Management
```
GET /api/v1/tags - Get all tags
GET /api/v1/tags/search - Search tags by name
GET /api/v1/tags/{tag_id} - Get specific tag
POST /api/v1/tags/refresh - Refresh tags from server
GET /api/v1/tags/status - Get tag manager status
```

**Removed Endpoints** (Now Frontend-Only):
- ~~GET /api/v1/overlay/states~~ - Overlays managed by frontend
- ~~POST /api/v1/overlay/*/toggle~~ - Overlay control via frontend
- ~~GET /api/v1/hotkeys~~ - Hotkeys handled by frontend
- ~~POST /api/v1/hotkeys/*~~ - Hotkey management in frontend

### WebSocket Communication
- **Purpose**: Real-time communication with PyQt6 frontend
- **Context**: Backend sends context data when requested
- **AI**: Backend receives AI messages from frontend
- **No Overlay Control**: Frontend manages overlays independently

**WebSocket Message Types**:
```json
// Context request
{"type": "get_context"}

// AI message
{"type": "ai_message", "text": "Hello", "smarter_analysis": false}

// Context search
{"type": "search_context", "ocr_text": "extracted text"}
```

## Removed Components (Architecture Cleanup)

### **Deleted Files:**
- ❌ `services/overlay_manager.py` - Overlay management moved to frontend
- ❌ `settings/theme_manager.py` - Theme management moved to frontend

### **Removed Functionality:**
- **Overlay State Management**: Frontend manages overlay windows directly
- **Theme Management**: UI themes handled by frontend only  
- **GUI Preferences**: Visual settings managed by frontend
- **Overlay API Endpoints**: No backend overlay control needed
- **WebSocket Overlay Coordination**: Frontend handles overlay state independently

### **Benefits of Cleanup:**
1. **Clear Separation**: Backend = Logic, Frontend = GUI
2. **Reduced Complexity**: No redundant overlay state synchronization
3. **Better Performance**: Frontend controls GUI without backend latency
4. **Platform Independence**: Backend no longer tied to specific UI frameworks
5. **Easier Maintenance**: GUI logic consolidated in frontend

## Ubuntu/Wayland Specific Features

### Screenshot Processing
- **Frontend**: PyQt6 handles screenshot capture across different display servers
- **Backend**: Platform-agnostic OCR processing via API
- **Integration**: Base64 image transfer via HTTP/WebSocket

### System Integration
- **Backend**: Desktop notifications via notify-send
- **Backend**: System tray integration for Linux
- **Backend**: Clipboard text detection (frontend provides selected text)
- **Frontend**: All GUI interactions and window management

## Required Permissions

**Backend Permissions** (automatically checked):
- **Clipboard Access**: xclip for text detection
- **Notifications**: Desktop notification support  
- **System Tray**: System tray icon display

**Frontend Permissions** (handled by PyQt6):
- **Screenshot Access**: Display server screenshot capabilities
- **Input Events**: Global hotkey detection via evdev
- **Window Management**: Overlay window positioning and display

## Development

### Adding New Backend Features
1. **Business Logic**: Add to appropriate service in `services/`
2. **API Endpoints**: Add routes to `api/routes.py`
3. **Data Models**: Update models in `models/`

### Frontend-Backend Communication
1. **API Calls**: Use REST endpoints for one-time operations
2. **WebSocket**: Use for real-time communication and context requests
3. **Screenshot Processing**: Frontend captures → Base64 → Backend API → OCR

### Testing Backend
```bash
# Start backend server
python main.py

# Test API endpoints
curl http://103.42.50.224:8000/api/v1/health

# Test WebSocket
wscat -c ws://localhost:8000/ws
```

## Integration with Frontend

### **Clear Responsibilities:**

**Backend** (python-backend/):
- AI communication and response processing
- OCR text extraction from images
- Context analysis and search
- Authentication and user management
- System notifications and tray integration

**Frontend** (python-frontend/):
- All overlay windows and GUI elements
- Screenshot capture and image handling
- Global hotkey detection and handling
- Theme management and visual styling
- User preferences and UI configuration

### **Data Flow Examples:**

**Screenshot → OCR:**
```
Frontend: Screenshot → Base64 → POST /api/v1/screenshot/process
Backend: OCR Processing → Text Extraction → JSON Response
Frontend: Display Results in Overlay
```

**AI Chat:**
```
Frontend: User Input → POST /api/v1/ai/send-message  
Backend: Context + AI Processing → AI Response
Frontend: Display Response in Chat Overlay
```

**Context Search:**
```
Frontend: OCR Text → WebSocket {"type": "search_context"}
Backend: Context Search → Notes Discovery
Frontend: Display Context in Auto Context Overlay
```

## Configuration

### Environment Variables
```bash
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# Backend Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=True

# JWT Configuration
JWT_SECRET_KEY=your_jwt_secret_here
```

### Backend Settings (GUI-Free)
- **Logging**: `~/.horizon-ai/logs/horizon-ai.log`
- **Authentication**: `~/.horizon-ai/auth.json`
- **Core Preferences**: `~/.config/horizon-overlay/preferences.json`

### Frontend Settings (GUI-Specific)
- **Theme Configuration**: Handled by frontend settings
- **Overlay Preferences**: Managed by frontend configuration
- **Hotkey Mappings**: Stored in frontend settings
- **UI Layout**: Frontend-specific configuration

## Troubleshooting

### Common Issues

1. **OCR Not Working**
   ```bash
   sudo apt install tesseract-ocr tesseract-ocr-eng
   ```

2. **API Connection Failed**
   - Check if backend is running on port 8000
   - Verify frontend can reach `http://103.42.50.224:8000`
   - Check backend logs for errors

3. **Context Processing Issues**
   - Ensure frontend sends screenshots in Base64 format
   - Check OCR processor has sufficient memory
   - Verify image format compatibility

4. **GUI Issues**
   - **Solution**: GUI problems are frontend-only
   - Check frontend logs and PyQt6 configuration
   - Backend only handles data processing

## Next Steps

1. **Enhanced Context Analysis**: Improve semantic understanding
2. **Performance Optimization**: Caching and async improvements  
3. **Security Hardening**: Enhanced authentication and authorization
4. **API Expansion**: Additional context processing endpoints
5. **Cross-Platform API**: Platform-agnostic service layer for multiple frontends