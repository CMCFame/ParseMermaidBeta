"""
Enhanced OpenAI converter with IVR-specific capabilities
"""
import os
import re
import logging
import base64
import io
from typing import Optional
from PIL import Image
from pdf2image import convert_from_path
import streamlit as st
from openai import OpenAI

class IVRPromptLibrary:
    """Enhanced prompting for exact IVR diagram reproduction"""
    
    SYSTEM_PROMPT = """You are a specialized converter focused on creating EXACT, VERBATIM Mermaid.js flowchart representations of IVR call flow diagrams. Your task is to reproduce the input diagram with 100% accuracy, maintaining all text, connections, and flow logic exactly as shown.

CRITICAL REQUIREMENTS:
1. Text Content:
   - Copy ALL text exactly as written, including punctuation and capitalization
   - Use <br/> for line breaks within nodes
   - Preserve parentheses, special characters, and spacing
   - Include all numbers and reference texts (e.g., "page 25", "Level 2")

2. Node Types:
   - Decision diamonds: Use {"text"} for any decision/question nodes
   - Process rectangles: Use ["text"] for standard process nodes
   - Maintain exact node shapes as shown in the original

3. Connections:
   - Preserve ALL connection labels exactly as written
   - Include retry loops and self-references
   - Maintain connection directions
   - Copy specific button press labels (e.g., "Press 1", "7 - not home")

4. Document Elements:
   - Include headers, titles, and subtitles
   - Preserve footer text and company information
   - Include all notes and references
   - Maintain page numbers and section references

5. Special Elements:
   - Include conditional logic text exactly as shown
   - Preserve system messages and prompts
   - Maintain error handling paths
   - Keep timeout and retry logic

EXAMPLE FORMAT:
flowchart TD
    A["Exact Node Text<br/>With line breaks<br/>And formatting"] -->|"Exact Label Text"| B{"Decision Text<br/>With Options"}
    B -->|"1 - exact option"| C["Next Step"]
    B -->|"retry"| A

ERROR PREVENTION:
- Do not summarize or simplify text
- Do not modify connection logic
- Do not omit any elements
- Do not change terminology
- Do not rearrange the flow

OUTPUT REQUIREMENTS:
- Must start with: flowchart TD
- Use correct Mermaid.js syntax
- Preserve exact diagram structure
- Include all original elements
- Maintain visual hierarchy"""

    ERROR_RECOVERY = """If conversion is unclear:
1. Focus on exact text reproduction first
2. Maintain all connection paths exactly
3. Preserve decision logic precisely
4. Keep all labeling and numbering
5. Include every element shown"""

class ImageProcessor:
    """Enhanced image processing capabilities"""
    
    @staticmethod
    def process_image(image_path: str, max_size: tuple = (1000, 1000)) -> Image.Image:
        """Process and optimize image for conversion"""
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Resize if too large
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Enhance contrast for better text recognition
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            
            return img

    @staticmethod
    def pdf_to_image(pdf_path: str, dpi: int = 200) -> Image.Image:
        """Convert PDF to image with optimization"""
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        if not images:
            raise ValueError("Failed to extract image from PDF")
        return images[0]

class FlowchartConverter:
    """Enhanced OpenAI-powered flowchart converter"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize converter with API key"""
        self.api_key = (
            api_key or 
            st.secrets.get("OPENAI_API_KEY") or 
            os.getenv("OPENAI_API_KEY")
        )
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found")
        
        self.client = OpenAI(api_key=self.api_key)
        self.logger = logging.getLogger(__name__)
        self.image_processor = ImageProcessor()

    def convert_diagram(self, file_path: str) -> str:
        """
        Convert flow diagram to Mermaid syntax
        
        Args:
            file_path: Path to diagram file
            
        Returns:
            str: Mermaid diagram syntax
        """
        try:
            # Validate file
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            file_ext = os.path.splitext(file_path)[1].lower()
            supported_formats = {'.pdf', '.png', '.jpg', '.jpeg'}
            
            if file_ext not in supported_formats:
                raise ValueError(f"Unsupported format. Supported: {supported_formats}")
            
            # Process image
            if file_ext == '.pdf':
                image = self.image_processor.pdf_to_image(file_path)
            else:
                image = self.image_processor.process_image(file_path)
            
            # Convert to base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            base64_image = base64.b64encode(buffered.getvalue()).decode()
            
            # Make API call
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": IVRPromptLibrary.SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Convert this IVR flow diagram to Mermaid syntax EXACTLY as shown. Maintain all text, connections, and formatting precisely."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.1  # Low temperature for more precise output
            )
            
            # Extract and clean Mermaid code
            mermaid_text = self._clean_mermaid_code(
                response.choices[0].message.content
            )
            
            # Validate syntax
            if not self._validate_mermaid_syntax(mermaid_text):
                # Try recovery with simpler conversion
                self.logger.warning("Initial conversion failed validation, attempting recovery")
                return self._attempt_recovery_conversion(base64_image)
            
            return mermaid_text
            
        except Exception as e:
            self.logger.error(f"Conversion failed: {str(e)}")
            raise RuntimeError(f"Diagram conversion error: {str(e)}")

    def _clean_mermaid_code(self, raw_text: str) -> str:
        """Clean and format Mermaid code"""
        # Extract code from markdown blocks if present
        code_match = re.search(r'```(?:mermaid)?\n(.*?)```', raw_text, re.DOTALL)
        if code_match:
            raw_text = code_match.group(1)
        
        # Ensure proper flowchart definition
        if not raw_text.strip().startswith('flowchart TD'):
            raw_text = f'flowchart TD\n{raw_text}'
        
        # Clean up whitespace and empty lines
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return '\n'.join(lines)

    def _validate_mermaid_syntax(self, mermaid_text: str) -> bool:
        """Validate basic Mermaid syntax"""
        required_elements = [
            r'flowchart\s+TD',    # Must have flowchart definition
            r'\w+\s*[\["{\(]',    # Must have at least one node
            r'-->'                # Must have at least one connection
        ]
        
        return all(re.search(pattern, mermaid_text) for pattern in required_elements)

    def _attempt_recovery_conversion(self, base64_image: str) -> str:
        """Attempt simplified conversion for recovery"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"{IVRPromptLibrary.SYSTEM_PROMPT}\n{IVRPromptLibrary.ERROR_RECOVERY}"
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Convert this diagram with exact text reproduction and maintain all connections precisely."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096,
                temperature=0.3  # Slightly higher temperature for recovery
            )
            
            return self._clean_mermaid_code(
                response.choices[0].message.content
            )
            
        except Exception as e:
            raise RuntimeError(f"Recovery conversion failed: {str(e)}")

def process_flow_diagram(file_path: str, api_key: Optional[str] = None) -> str:
    """Convenience wrapper for diagram conversion"""
    converter = FlowchartConverter(api_key)
    return converter.convert_diagram(file_path)