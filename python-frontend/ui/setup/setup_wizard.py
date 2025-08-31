"""
Setup Wizard for initial application configuration
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QStackedWidget, QWidget, QLineEdit,
                            QCheckBox, QSpacerItem, QSizePolicy, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap


class SetupWizard(QDialog):
    """Setup wizard for first-time application configuration"""
    
    setup_completed = pyqtSignal()
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.current_page = 0
        
        self.setWindowTitle("Horizon Overlay Setup")
        self.setFixedSize(600, 400)
        self.setModal(True)
        
        self._setup_ui()
        self._setup_pages()
        
    def _setup_ui(self):
        """Setup the main UI"""
        layout = QVBoxLayout()
        
        # Header
        header_label = QLabel("Welcome to Horizon Overlay")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_font = QFont()
        header_font.setPointSize(18)
        header_font.setBold(True)
        header_label.setFont(header_font)
        
        # Stacked widget for pages
        self.pages_stack = QStackedWidget()
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self._go_back)
        self.back_button.setEnabled(False)
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self._go_next)
        
        self.finish_button = QPushButton("Finish")
        self.finish_button.clicked.connect(self._finish_setup)
        self.finish_button.setVisible(False)
        
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.next_button)
        nav_layout.addWidget(self.finish_button)
        
        # Add to main layout
        layout.addWidget(header_label)
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        layout.addWidget(self.pages_stack)
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        layout.addLayout(nav_layout)
        
        self.setLayout(layout)
        
    def _setup_pages(self):
        """Setup wizard pages"""
        # Welcome page
        welcome_page = self._create_welcome_page()
        self.pages_stack.addWidget(welcome_page)
        
        # Backend configuration page
        backend_page = self._create_backend_page()
        self.pages_stack.addWidget(backend_page)
        
        # Hotkeys configuration page
        hotkeys_page = self._create_hotkeys_page()
        self.pages_stack.addWidget(hotkeys_page)
        
        # Completion page
        completion_page = self._create_completion_page()
        self.pages_stack.addWidget(completion_page)
        
    def _create_welcome_page(self):
        """Create welcome page"""
        page = QWidget()
        layout = QVBoxLayout()
        
        # Welcome text
        welcome_text = QTextEdit()
        welcome_text.setReadOnly(True)
        welcome_text.setMaximumHeight(200)
        welcome_text.setHtml("""
        <h3>Welcome to Horizon Overlay!</h3>
        <p>This setup wizard will help you configure the application for first use.</p>
        <p><b>Features:</b></p>
        <ul>
        <li>AI-powered overlay assistance</li>
        <li>Quick screen capture and context extraction</li>
        <li>Customizable hotkeys and shortcuts</li>
        <li>Real-time system integration</li>
        </ul>
        <p>Click Next to begin the setup process.</p>
        """)
        
        layout.addWidget(welcome_text)
        layout.addStretch()
        
        page.setLayout(layout)
        return page
        
    def _create_backend_page(self):
        """Create backend configuration page"""
        page = QWidget()
        layout = QVBoxLayout()
        
        # Backend settings
        backend_label = QLabel("Backend Configuration")
        backend_label.setFont(QFont("", 14, QFont.Weight.Bold))
        
        # Host input
        host_label = QLabel("Backend Host:")
        self.host_input = QLineEdit("localhost")
        
        # Port input
        port_label = QLabel("Backend Port:")
        self.port_input = QLineEdit("8000")
        
        # Auto-connect checkbox
        self.auto_connect_checkbox = QCheckBox("Automatically connect to backend on startup")
        self.auto_connect_checkbox.setChecked(True)
        
        layout.addWidget(backend_label)
        layout.addSpacing(10)
        layout.addWidget(host_label)
        layout.addWidget(self.host_input)
        layout.addWidget(port_label)
        layout.addWidget(self.port_input)
        layout.addSpacing(10)
        layout.addWidget(self.auto_connect_checkbox)
        layout.addStretch()
        
        page.setLayout(layout)
        return page
        
    def _create_hotkeys_page(self):
        """Create hotkeys configuration page"""
        page = QWidget()
        layout = QVBoxLayout()
        
        # Hotkeys settings
        hotkeys_label = QLabel("Hotkey Configuration")
        hotkeys_label.setFont(QFont("", 14, QFont.Weight.Bold))
        
        # Default hotkeys info
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setMaximumHeight(150)
        info_text.setHtml("""
        <h4>Default Hotkeys:</h4>
        <ul>
        <li><b>Ctrl+Shift+A</b> - AI Assist overlay</li>
        <li><b>Ctrl+Shift+C</b> - Quick capture</li>
        <li><b>Ctrl+Shift+X</b> - Auto context</li>
        </ul>
        <p>You can customize these hotkeys later in the settings.</p>
        """)
        
        # Enable hotkeys checkbox
        self.enable_hotkeys_checkbox = QCheckBox("Enable global hotkeys")
        self.enable_hotkeys_checkbox.setChecked(True)
        
        layout.addWidget(hotkeys_label)
        layout.addSpacing(10)
        layout.addWidget(info_text)
        layout.addSpacing(10)
        layout.addWidget(self.enable_hotkeys_checkbox)
        layout.addStretch()
        
        page.setLayout(layout)
        return page
        
    def _create_completion_page(self):
        """Create setup completion page"""
        page = QWidget()
        layout = QVBoxLayout()
        
        # Completion message
        completion_label = QLabel("Setup Complete!")
        completion_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        completion_label.setFont(QFont("", 16, QFont.Weight.Bold))
        
        completion_text = QTextEdit()
        completion_text.setReadOnly(True)
        completion_text.setMaximumHeight(150)
        completion_text.setHtml("""
        <h4>Horizon Overlay is now ready to use!</h4>
        <p>The application will start minimized to the system tray.</p>
        <p>Right-click the tray icon to access overlay functions or quit the application.</p>
        <p>You can change settings anytime from the system tray menu.</p>
        """)
        
        layout.addWidget(completion_label)
        layout.addSpacing(20)
        layout.addWidget(completion_text)
        layout.addStretch()
        
        page.setLayout(layout)
        return page
        
    def _go_back(self):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.pages_stack.setCurrentIndex(self.current_page)
            self._update_navigation()
            
    def _go_next(self):
        """Go to next page"""
        if self.current_page < self.pages_stack.count() - 1:
            self.current_page += 1
            self.pages_stack.setCurrentIndex(self.current_page)
            self._update_navigation()
            
    def _update_navigation(self):
        """Update navigation button states"""
        # Back button
        self.back_button.setEnabled(self.current_page > 0)
        
        # Next/Finish buttons
        is_last_page = self.current_page == self.pages_stack.count() - 1
        self.next_button.setVisible(not is_last_page)
        self.finish_button.setVisible(is_last_page)
        
    def _finish_setup(self):
        """Complete the setup process"""
        # Save settings
        if hasattr(self, 'host_input'):
            self.settings.backend.host = self.host_input.text()
        if hasattr(self, 'port_input'):
            self.settings.backend.port = int(self.port_input.text())
        if hasattr(self, 'auto_connect_checkbox'):
            self.settings.backend.auto_connect = self.auto_connect_checkbox.isChecked()
        if hasattr(self, 'enable_hotkeys_checkbox'):
            self.settings.hotkeys.enabled = self.enable_hotkeys_checkbox.isChecked()
            
        self.setup_completed.emit()
        self.accept()
        
    def exec(self):
        """Override exec to return setup completion status"""
        result = super().exec()
        return result == QDialog.DialogCode.Accepted