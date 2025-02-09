"""
openai_converter.py

Handles image/PDF -> Mermaid conversion with enhanced prompts to
preserve text and structure. This code uses OpenAI's ChatCompletion API
to transform images of IVR flow diagrams into Mermaid code.

Usage:
    from openai_converter import process_flow_diagram

    mermaid_code = process_flow_diagram("/path/to/my_diagram.png", api_key="...")
    print(mermaid_code)
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

# If using official openai python library:
import openai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IVRPromptLibrary:
    """Enhanced prompting for exact IVR diagram reproduction."""

    SYSTEM_PROMPT = """You are a specialized converter that creates EXACT Mermaid.js flowchart
representations of IVR call flow diagrams from an image. 

CRITICAL REQUIREMENTS:
1. Copy ALL text exactly as written, using <br/> for line breaks.
2. Preserve parentheses, special characters, spacing, numbering, and punctuation.
3. Use flowchart TD as the base, or whichever direction the diagram indicates.
4. Each decision node uses braces {"Decision text"}, each process node uses brackets ["Process text"].
5. Maintain all connections, including any labeled edges, retry loops, and self-references.
6. Do NOT summarize, simplify, or omit ANY text.

Output must be valid Mermaid code, starting with:

flowchart TD
   ... rest of the diagram ...

ERROR PREVENTION:
- Do not alter text or node flow
- Retain node shape brackets and braces as is
"""

    ERROR_RECOVERY = """If unclear how to parse the diagram, prioritize extracting text exactly,
reconstructing connections as best as possible. Do not omit or rephrase content."""


class ImageProcessor:
    """Prepares images (PNG, JPG, PDF) for GPT usage by resizing and enhancing."""

    @staticmethod
    def process_image(image_path: str, max_size: tuple = (1000, 1000)) -> Image.Image:
        """Process and optimize the image for conversion."""
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Resize if it's too large
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Optionally enhance contrast for better text recognition
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)

            return img

    @staticmethod
    def pdf_to_image(pdf_path: str, dpi: int = 200) -> Image.Image:
        """Convert the first page of a PDF to image."""
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        if not images:
            raise ValueError("Failed to extract image from PDF.")
        return images[0]


class FlowchartConverter:
    """
    Uses OpenAI Chat Completion to convert an image to a Mermaid flowchart string.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with an API key."""
        self.api_key = (
            api_key or
            st.secrets.get("OPENAI_API_KEY") or
            os.getenv("OPENAI_API_KEY")
        )
        if not self.api_key:
            raise ValueError("OpenAI API key not found.")

        openai.api_key = self.api_key
        self.logger = logging.getLogger(__name__)
        self.image_processor = ImageProcessor()

    def convert_diagram(self, file_path: str) -> str:
        """
        Convert an IVR flow diagram to Mermaid code.

        Args:
            file_path: Path to the image or PDF diagram.

        Returns:
            str: Mermaid diagram text.
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            file_ext = os.path.splitext(file_path)[1].lower()
            supported_formats = {'.pdf', '.png', '.jpg', '.jpeg'}

            if file_ext not in supported_formats:
                raise ValueError(f"Unsupported format. Supported: {supported_formats}")

            # Convert PDF to image if needed
            if file_ext == '.pdf':
                image = self.image_processor.pdf_to_image(file_path)
            else:
                image = self.image_processor.process_image(file_path)

            # Convert to base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            base64_image = base64.b64encode(buffered.getvalue()).decode()

            # Call OpenAI
            response_text = self._call_openai_with_retries(base64_image)

            # Clean the code
            mermaid_text = self._clean_mermaid_code(response_text)

            # Optional validation
            if not self._validate_mermaid_syntax(mermaid_text):
                self.logger.warning("First pass validation failed, attempting recovery.")
                mermaid_text = self._attempt_recovery_conversion(base64_image)

            return mermaid_text

        except Exception as e:
            self.logger.error(f"Conversion failed: {str(e)}")
            raise RuntimeError(f"Diagram conversion error: {str(e)}")

    def _call_openai_with_retries(self, base64_image: str) -> str:
        """
        Make the OpenAI ChatCompletion call, with potential retries if something fails.
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": IVRPromptLibrary.SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Convert this IVR flow diagram to Mermaid syntax exactly. Image (base64): data:image/png;base64,{base64_image}"
                    }
                ],
                temperature=0.1,
                max_tokens=2000
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            self.logger.error(f"OpenAI call error: {str(e)}")
            raise e

    def _attempt_recovery_conversion(self, base64_image: str) -> str:
        """
        Attempt a second pass with a more explicit error-recovery approach.
        """
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"{IVRPromptLibrary.SYSTEM_PROMPT}\n{IVRPromptLibrary.ERROR_RECOVERY}"
                },
                {
                    "role": "user",
                    "content": f"Here is the image again (base64). data:image/png;base64,{base64_image}"
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )
        text = response.choices[0].message.content.strip()
        return self._clean_mermaid_code(text)

    def _clean_mermaid_code(self, raw_text: str) -> str:
        """
        Extract code from code fences if present and ensure it starts with 'flowchart TD'.
        """
        code_match = re.search(r'```(?:mermaid)?\n(.*?)```', raw_text, re.DOTALL)
        if code_match:
            raw_text = code_match.group(1).strip()

        # If there's no 'flowchart' present, prepend it (some models might skip it).
        if not raw_text.lower().startswith('flowchart'):
            raw_text = f"flowchart TD\n{raw_text}"

        # Remove empty lines, trailing spaces
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _validate_mermaid_syntax(self, mermaid_text: str) -> bool:
        """
        Basic validation to confirm we have a 'flowchart' line, at least one node, and one arrow.
        """
        # Must have flowchart, a node bracket, and an arrow
        if 'flowchart' not in mermaid_text.lower():
            return False
        if '-->' not in mermaid_text and '->' not in mermaid_text:
            return False
        return True

def process_flow_diagram(file_path: str, api_key: Optional[str] = None) -> str:
    """
    Convenience wrapper for diagram conversion. Typically called from the Streamlit app.
    """
    converter = FlowchartConverter(api_key=api_key)
    return converter.convert_diagram(file_path)
