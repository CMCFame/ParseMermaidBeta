"""
openai_ivr_converter.py

Refined module for converting Mermaid diagrams (or parsed Mermaid data)
into a custom IVR JavaScript configuration. We provide a structured approach
for 1:1 mapping, reducing GPT's tendency to summarize or omit data.
"""

import json
import logging
from typing import Dict

# If using official openai python library:
import openai

from parse_mermaid import parse_mermaid

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT_IVR = """You are an expert IVR system developer. 
You MUST produce a 1-to-1 mapping from each parsed Mermaid node to an IVR config object, preserving every bit of text.

Requirements for the IVR config array:
1. The final output must be valid JavaScript in the form:

module.exports = [
  {...},
  {...},
  ...
];

2. Each object must have a unique "label" property that maps to the Mermaid node ID (e.g. A, B, C).
3. Include a "log" or "playPrompt" array that uses the entire raw_text from the node. 
   - If there's a long text, you can store it in "log" or split it among multiple "playPrompt" items.
4. If there's an arrow from Node A to Node B labeled "Press 1", then in the A node's config, you must handle that branch, e.g.:

{
   "label": "A",
   "log": "Some text",
   "branch": [
     { "condition": "digits=='1'", "goto": "B" }
   ]
}

5. Do NOT omit any text or branching details. 
6. Return only the JavaScript code starting with module.exports = [ and ending with ]; 
   No extra commentary or markdown fences.
7. Do NOT rename or summarize node text. Keep punctuation, numbers, parentheses, line breaks (<br/>) exact.

If anything is unclear, ask for clarification. Otherwise, produce the final code directly.
"""


def structured_nodes_to_ivr(parsed_data: Dict, api_key: str) -> str:
    """
    Uses GPT to convert the *structured* Mermaid data (nodes, edges, etc.)
    into a 1:1 IVR JavaScript config.

    Args:
        parsed_data: The dictionary from parse_mermaid() containing 'nodes' and 'edges'.
        api_key: OpenAI API key.

    Returns:
        A string containing the final "module.exports = [ ... ];" code.
    """
    openai.api_key = api_key

    # Prepare a JSON representation of the parsed data to feed GPT.
    # We can sanitize or limit the content if needed, but ideally we keep it all.
    structured_json = {
        "nodes": [],
        "edges": []
    }

    # Flatten nodes into a list for easier reading by GPT
    for node_id, node_obj in parsed_data["nodes"].items():
        structured_json["nodes"].append({
            "id": node_id,
            "raw_text": node_obj.raw_text,
            "node_type": node_obj.node_type.name  # e.g. DECISION, ACTION, etc.
        })

    # Edges as a list
    for edge in parsed_data["edges"]:
        structured_json["edges"].append({
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "label": edge.label
        })

    # Convert to a JSON string for GPT
    # We can embed it directly in the user prompt.
    parsed_data_str = json.dumps(structured_json, indent=2)

    user_prompt = f"""
Below is the structured Mermaid data (nodes and edges).
Convert each node into an IVR config object, preserving all text in raw_text
and referencing edges for branches. Please produce only the JavaScript code 
in the specified format.

Parsed Data (JSON):
{parsed_data_str}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT_IVR
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0.0,
            max_tokens=3000
        )
        ivr_code = response.choices[0].message.content.strip()

        # Basic validation check
        if not ivr_code.startswith("module.exports = [") or not ivr_code.endswith("];"):
            raise ValueError("GPT returned code that does not start/end with module.exports = [ ... ];")

        # Attempt to parse the JSON inside "module.exports = [ ... ];" to ensure validity
        # We'll slice out the array portion.
        inner_part = ivr_code[len("module.exports = "):]
        inner_part = inner_part.strip("; \n")
        # Now inner_part should be "[ {...}, {...} ]"
        # We'll try to parse it as JSON
        try:
            _ = json.loads(inner_part)
        except json.JSONDecodeError as je:
            logger.warning(f"Could not parse returned IVR code as JSON. Error: {je}")
            # We can either raise or allow it and show partial code
            raise ValueError("IVR code is not valid JSON inside the array.")

        return ivr_code

    except Exception as e:
        logger.error(f"IVR conversion failed: {str(e)}")
        # Return a fallback code snippet, or re-raise
        raise RuntimeError(f"structured_nodes_to_ivr error: {str(e)}")


def convert_mermaid_to_ivr(mermaid_code: str, api_key: str) -> str:
    """
    A convenience function to parse Mermaid text, then feed the structured data to GPT.
    This mimics the old approach but ensures 1:1 mapping via the structured data pipeline.

    Args:
        mermaid_code: The raw Mermaid code to convert.
        api_key: OpenAI API key.

    Returns:
        JavaScript string with module.exports = [ ... ];
    """
    parsed = parse_mermaid(mermaid_code)
    return structured_nodes_to_ivr(parsed, api_key)
