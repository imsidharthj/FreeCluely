"""
Screenshot capture using pyscreenshot for in-memory image handling.
"""
import logging
from typing import Optional, Dict, Any
import base64
import io

# pyscreenshot is a wrapper for various backend libraries (e.g., Pillow on Linux/Wayland)
import pyscreenshot as ImageGrab
from PIL.Image import Image

class ScreenshotManager:
    """
    Manages screenshot capture using pyscreenshot for a simple, cross-platform approach.
    This implementation captures the screen directly into a PIL Image object in memory,
    avoiding the need to save files to disk.
    """

    def __init__(self, backend_client=None):
        """Initializes the ScreenshotManager."""
        self.logger = logging.getLogger(__name__)
        self.backend_client = backend_client
        self.logger.info("ScreenshotManager initialized using pyscreenshot.")

    def capture_screen(self) -> Optional[Image]:
        """
        Captures the entire screen and returns it as a Pillow Image object.

        Returns:
            A Pillow (PIL) Image object of the screenshot, or None if capture fails.
        """
        self.logger.debug("Attempting to capture screen.")
        try:
            # pyscreenshot.grab() captures the full screen and returns a PIL Image
            screenshot = ImageGrab.grab()
            if screenshot:
                self.logger.info("Screen captured successfully into memory.")
                return screenshot
            else:
                self.logger.error("Screen capture failed: grab() returned None.")
                return None
        except Exception as e:
            # This can catch backend issues, like if Wayland is not properly supported
            # by the underlying library (though Pillow usually works).
            self.logger.critical(f"An unexpected error occurred during screen capture: {e}", exc_info=True)
            return None
    
    def image_to_bytes(self, image: Image, format: str = 'PNG', quality: int = 95) -> bytes:
        """
        Convert PIL Image to bytes.
        
        Args:
            image: PIL Image object
            format: Image format ('PNG', 'JPEG', etc.)
            quality: JPEG quality (1-100), ignored for PNG
            
        Returns:
            bytes: Image data as bytes
        """
        try:
            buffer = io.BytesIO()
            
            if format.upper() == 'JPEG':
                # Convert to RGB if needed for JPEG
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
                image.save(buffer, format=format, quality=quality)
            else:
                # PNG format (default)
                image.save(buffer, format=format)
            
            buffer.seek(0)
            image_bytes = buffer.getvalue()
            
            self.logger.debug(f"Image converted to {len(image_bytes)} bytes in {format} format")
            return image_bytes
            
        except Exception as e:
            self.logger.error(f"Failed to convert image to bytes: {e}")
            raise
    
    def image_to_base64(self, image: Image, format: str = 'PNG') -> str:
        """
        Convert PIL Image to base64 string.
        
        Args:
            image: PIL Image object
            format: Image format ('PNG', 'JPEG', etc.)
            
        Returns:
            str: Base64 encoded image data
        """
        try:
            image_bytes = self.image_to_bytes(image, format)
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            
            self.logger.debug(f"Image converted to base64 string ({len(base64_string)} characters)")
            return base64_string
            
        except Exception as e:
            self.logger.error(f"Failed to convert image to base64: {e}")
            raise
    
    async def send_screenshot_to_backend(self, image: Image, preprocess: bool = True, extract_blocks: bool = False) -> Optional[Dict[str, Any]]:
        """
        Send screenshot to backend for OCR processing.
        
        Args:
            image: PIL Image object to process
            preprocess: Whether to apply image preprocessing for better OCR
            extract_blocks: Whether to extract structured text blocks
            
        Returns:
            Dict containing OCR results or None if failed
        """
        if not self.backend_client:
            self.logger.error("Backend client not configured")
            return None
        
        try:
            # Convert image to base64
            base64_data = self.image_to_base64(image, format='PNG')
            
            # Send to backend
            response = await self.backend_client.process_screenshot(
                image_data=base64_data,
                preprocess=preprocess,
                extract_blocks=extract_blocks
            )
            
            if response.success:
                self.logger.info(f"Screenshot processed successfully. OCR confidence: {response.data.get('confidence', 0):.2f}")
                return response.data
            else:
                self.logger.error(f"Backend processing failed: {response.error}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to send screenshot to backend: {e}")
            return None
    
    async def capture_and_process(self, preprocess: bool = True, extract_blocks: bool = False) -> Optional[Dict[str, Any]]:
        """
        Capture screenshot and immediately send to backend for processing.
        
        Args:
            preprocess: Whether to apply image preprocessing for better OCR
            extract_blocks: Whether to extract structured text blocks
            
        Returns:
            Dict containing OCR results or None if failed
        """
        try:
            # Capture screenshot
            screenshot = self.capture_screen()
            if not screenshot:
                self.logger.error("Failed to capture screenshot")
                return None
            
            # Send to backend for processing
            result = await self.send_screenshot_to_backend(
                screenshot, 
                preprocess=preprocess, 
                extract_blocks=extract_blocks
            )
            
            if result:
                self.logger.info("Screenshot captured and processed successfully")
                return result
            else:
                self.logger.error("Failed to process screenshot")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to capture and process screenshot: {e}")
            return None
    
    def set_backend_client(self, backend_client):
        """
        Set or update the backend client for API communication.
        
        Args:
            backend_client: Backend client instance
        """
        self.backend_client = backend_client
        self.logger.info("Backend client configured for ScreenshotManager")
    
    async def get_ocr_text_only(self, image: Optional[Image] = None) -> str:
        """
        Get only the OCR text from screenshot (convenience method).
        
        Args:
            image: Optional PIL Image. If None, captures new screenshot
            
        Returns:
            str: Extracted text or empty string if failed
        """
        try:
            if image is None:
                image = self.capture_screen()
                if not image:
                    return ""
            
            result = await self.send_screenshot_to_backend(image, preprocess=True)
            
            if result and 'ocr_text' in result:
                return result['ocr_text']
            
            return ""
            
        except Exception as e:
            self.logger.error(f"Failed to get OCR text: {e}")
            return ""
