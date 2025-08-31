"""
AI Context Manager - Python equivalent of AIContextManager.swift
Handles OCR, selected text, and browser URL detection for Ubuntu/Wayland
FRONTEND HANDLES SCREENSHOTS - Backend only processes external screenshots
"""

import asyncio
import subprocess
from typing import Optional, Dict, Any
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import base64

from models.context_data import ContextData
from capture.ocr_processor import OCRProcessor


class AIContextManager:
    """Manages contextual information processing - Ubuntu/Wayland version"""
    
    def __init__(self):
        self.selected_text: str = ""
        self.ocr_text: str = ""
        self.image_bytes: Optional[bytes] = None
        self.browser_url: str = ""
        self.did_change_selected_text: bool = False
        
        # OCR processor only - no screen capture
        self.ocr_processor = OCRProcessor()

    async def capture_current_context(self, capture_image: bool = True) -> ContextData:
        """
        Capture context WITHOUT screenshot (frontend provides screenshots)
        
        Args:
            capture_image: Ignored - frontend handles screenshots
            
        Returns:
            ContextData: Context without image data (frontend will provide separately)
        """
        # Capture selected text
        selected = await self.capture_selected_text()
        self.selected_text = selected
        
        # Capture browser URL
        browser_url = await self.get_active_browser_url()
        self.browser_url = browser_url
        
        # No internal screenshot capture - frontend provides images
        self.image_bytes = None
        self.ocr_text = ""
        
        return ContextData(
            selected_text=self.selected_text,
            ocr_text=self.ocr_text,
            browser_url=self.browser_url,
            image_data=None  # Frontend will provide via separate API
        )

    async def capture_selected_text(self) -> str:
        """
        Capture currently selected text using clipboard - Ubuntu equivalent
        """
        try:
            # Use xclip to get current selection
            result = subprocess.run(
                ['xclip', '-selection', 'clipboard', '-o'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                selected_text = result.stdout.strip()
                
                # Check if selected text changed
                if selected_text != self.selected_text:
                    self.did_change_selected_text = True
                    print(f"Selected text changed: {selected_text[:50]}...")
                
                return selected_text
            else:
                return ""
                
        except subprocess.TimeoutExpired:
            print("Timeout getting selected text")
            return ""
        except FileNotFoundError:
            print("xclip not found - install with: sudo apt install xclip")
            return ""
        except Exception as e:
            print(f"Error getting selected text: {e}")
            return ""

    async def perform_ocr(self, image_data: bytes) -> str:
        """
        Perform OCR on image data using pytesseract
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            str: Extracted text from image
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to OpenCV format for preprocessing
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # Preprocess image for better OCR
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold to get better OCR results
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Perform OCR
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(thresh, config=custom_config)
            
            # Clean up the text
            cleaned_text = ' '.join(text.split())
            return cleaned_text
            
        except Exception as e:
            print(f"OCR processing failed: {e}")
            return ""

    async def get_active_browser_url(self) -> str:
        """
        Get URL from active browser tab - Ubuntu equivalent using window title parsing
        """
        try:
            # Get active window title using wmctrl
            result = subprocess.run(
                ['wmctrl', '-l'],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    # Look for browser windows in the title
                    if any(browser in line.lower() for browser in ['firefox', 'chrome', 'chromium', 'safari', 'edge']):
                        # Extract URL from title if present
                        url = self._extract_url_from_title(line)
                        if url:
                            return url
            
            return ""
            
        except subprocess.TimeoutExpired:
            print("Timeout getting browser URL")
            return ""
        except FileNotFoundError:
            print("wmctrl not found - install with: sudo apt install wmctrl")
            return ""
        except Exception as e:
            print(f"Error getting browser URL: {e}")
            return ""

    def _extract_url_from_title(self, title: str) -> str:
        """Extract URL from browser window title"""
        import re
        
        # Look for URLs in the title
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, title)
        
        if match:
            return match.group(0)
        
        return ""

    async def process_external_screenshot(self, image_data: bytes, preprocess: bool = True) -> Dict[str, Any]:
        """
        Process external screenshot (from frontend) with OCR
        
        Args:
            image_data: Raw image bytes from frontend
            preprocess: Whether to apply image preprocessing
            
        Returns:
            Dict containing OCR results and metadata
        """
        try:
            # Store the external image
            self.image_bytes = image_data
            
            # Process with OCR
            ocr_result = await self.ocr_processor.extract_text(
                image_data, 
                preprocess=preprocess, 
                extract_blocks=True
            )
            
            # Update internal OCR text
            self.ocr_text = ocr_result.text
            
            # Get image info
            image = Image.open(io.BytesIO(image_data))
            
            return {
                "ocr_text": ocr_result.text,
                "confidence": ocr_result.confidence,
                "image_info": {
                    "width": image.width,
                    "height": image.height,
                    "format": image.format or "Unknown",
                    "size_bytes": len(image_data)
                },
                "processing_method": "external_upload"
            }
            
        except Exception as e:
            print(f"External screenshot processing failed: {e}")
            raise e

    async def capture_context_with_external_screenshot(self, image_data: bytes) -> ContextData:
        """
        Capture context using external screenshot instead of internal capture
        
        Args:
            image_data: Screenshot data from frontend
            
        Returns:
            ContextData: Complete context with external screenshot
        """
        # Capture selected text and browser URL as usual
        selected = await self.capture_selected_text()
        self.selected_text = selected
        
        browser_url = await self.get_active_browser_url()
        self.browser_url = browser_url
        
        # Process external screenshot
        await self.process_external_screenshot(image_data, preprocess=True)
        
        return ContextData(
            selected_text=self.selected_text,
            ocr_text=self.ocr_text,
            browser_url=self.browser_url,
            image_data=self.image_bytes
        )