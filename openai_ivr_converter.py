"""
Direct IVR conversion using OpenAI with specific IVR format handling
"""
from typing import Dict, List, Any
from openai import OpenAI
import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class OpenAIIVRConverter:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def convert_to_ivr(self, mermaid_code: str) -> str:
        """Convert Mermaid diagram to IVR configuration using GPT-4"""
        
        prompt = f"""You are an expert IVR system developer. Convert this Mermaid flowchart into a complete IVR JavaScript configuration following these exact requirements:

        The IVR system requires specific configuration format:

        1. Node Structure:
           - Each node must have a unique "label" (node identifier)
           - "log" property for documentation/logging
           - "playPrompt" array with callflow IDs
           - Optional properties based on node type:
             * getDigits: For input collection
             * branch: For conditional navigation
             * goto: For direct transitions
             * maxLoop: For retry limits
             * gosub: For subroutine calls
             * nobarge: For non-interruptible messages

        2. Audio Prompts:
           Use exact callflow IDs:
           - 1001: Welcome/initial message
           - 1008: PIN entry request
           - 1009: Invalid input/retry
           - 1010: Timeout message
           - 1167: Accept response
           - 1021: Decline response
           - 1266: Qualified no response
           - 1274: Electric callout info
           - 1019: Callout reason
           - 1232: Location information
           - 1265: Wait message
           - 1017: Not home message
           - 1316: Availability check
           - 1029: Goodbye message
           - 1351: Error message

        3. Input Handling:
           For getDigits nodes:
           {{
             "numDigits": <number>,
             "maxTries": <number>,
             "validChoices": "1|2|3",
             "errorPrompt": "callflow:1009",
             "timeoutPrompt": "callflow:1010"
           }}

        4. Call Flow Control:
           - Use "branch" for conditional paths
           - Use "goto" for direct transitions
           - Use "gosub" for subroutines like SaveCallResult
           - Include retry logic with maxLoop
           - Handle timeouts and errors

        5. Standard Response Codes:
           SaveCallResult parameters:
           - Accept: [1001, "Accept"]
           - Decline: [1002, "Decline"]
           - Not Home: [1006, "NotHome"]
           - Qualified No: [1145, "QualNo"]
           - Error: [1198, "Error Out"]

        Here's the Mermaid diagram to convert:

        {mermaid_code}

        Generate a complete IVR configuration that exactly matches this flow pattern.
        Return only the JavaScript code in the format:
        module.exports = [ ... ];"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert IVR system developer specialized in creating precise IVR configurations with specific callflow IDs and control structures."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent output
                max_tokens=4000
            )

            # Extract and clean the response
            ivr_code = response.choices[0].message.content.strip()
            
            # Extract just the JavaScript code
            if "module.exports = [" in ivr_code:
                start_idx = ivr_code.find("module.exports = [")
                end_idx = ivr_code.rfind("];") + 2
                ivr_code = ivr_code[start_idx:end_idx]

            # Validate basic structure
            if not (ivr_code.startswith("module.exports = [") and ivr_code.endswith("];")):
                raise ValueError("Invalid IVR code format generated")

            # Basic validation of node structure
            try:
                nodes = json.loads(ivr_code[16:-1])  # Remove module.exports = and ;
                if not isinstance(nodes, list):
                    raise ValueError("Generated code is not a valid node array")
                for node in nodes:
                    if not isinstance(node, dict) or 'label' not in node:
                        raise ValueError("Invalid node structure")
            except json.JSONDecodeError:
                raise ValueError("Generated code is not valid JSON")

            return ivr_code

        except Exception as e:
            logger.error(f"IVR conversion failed: {str(e)}")
            # Return a basic error handler node
            return '''module.exports = [
  {
    "label": "Problems",
    "log": "Error handler",
    "playPrompt": ["callflow:1351"],
    "goto": "Goodbye"
  }
];'''

def convert_mermaid_to_ivr(mermaid_code: str, api_key: str) -> str:
    """Wrapper function for Mermaid to IVR conversion"""
    converter = OpenAIIVRConverter(api_key)
    return converter.convert_to_ivr(mermaid_code)