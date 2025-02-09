"""
parse_mermaid.py

Enhanced Mermaid parser with IVR-specific functionality.
Returns a structured representation of the diagram, which can then be
fed to GPT or used for additional validation/processing. 

Usage:
    from parse_mermaid import parse_mermaid

    mermaid_diagram = '''flowchart TD
        A["Start"] --> B{"Decision"}
        B -->|yes| C["End"]
        B -->|no| A
    '''
    parsed_result = parse_mermaid(mermaid_diagram)
    print(parsed_result['nodes'])
    print(parsed_result['edges'])

Structured Output Schema:
{
    'nodes': {
        'A': Node(...),
        'B': Node(...),
        ...
    },
    'edges': [
        Edge(from_id='A', to_id='B', label=None, style=None, condition=None),
        ...
    ],
    'subgraphs': { ... },
    'metadata': {
        'title': None,
        'direction': 'TD',
        'styles': { ... }
    }
}
"""

import re
from enum import Enum, auto
from typing import Dict, List, Optional
from dataclasses import dataclass, field

class NodeType(Enum):
    """Extended node types for IVR flows"""
    START = auto()
    END = auto()
    ACTION = auto()
    DECISION = auto()
    INPUT = auto()
    TRANSFER = auto()
    SUBPROCESS = auto()
    MENU = auto()        # For menu options
    PROMPT = auto()      # For voice prompts
    ERROR = auto()       # For error handling
    RETRY = auto()       # For retry logic

@dataclass
class Node:
    """Enhanced node representation."""
    id: str
    raw_text: str
    node_type: NodeType
    style_classes: List[str] = field(default_factory=list)
    subgraph: Optional[str] = None
    properties: Dict[str, str] = field(default_factory=dict)

    def is_interactive(self) -> bool:
        """Check if node requires user interaction."""
        return self.node_type in {NodeType.INPUT, NodeType.MENU, NodeType.DECISION}

@dataclass
class Edge:
    """Enhanced edge representation."""
    from_id: str
    to_id: str
    label: Optional[str] = None
    style: Optional[str] = None
    condition: Optional[str] = None  # For conditional flows, e.g. "Press 1"

class MermaidParser:
    """Enhanced Mermaid parser with IVR focus."""

    def __init__(self):
        # Patterns for detecting different node types based on textual content
        self.node_patterns = {
            NodeType.START: [
                r'\bstart\b', r'\bbegin\b', r'\bentry\b', 
                r'\binitial\b', r'\bstart call\b'
            ],
            NodeType.END: [
                r'\bend\b', r'\bstop\b', r'\bdone\b', 
                r'\bterminate\b', r'\bend call\b', r'\bhangup\b'
            ],
            NodeType.DECISION: [
                r'\?', r'\{.*\}', r'\bchoice\b', r'\bif\b',
                r'\bpress\b', r'\bselect\b', r'\boption\b'
            ],
            NodeType.INPUT: [
                r'\binput\b', r'\benter\b', r'\bprompt\b', 
                r'\bget\b', r'\bdigits\b', r'\bpin\b'
            ],
            NodeType.TRANSFER: [
                r'\btransfer\b', r'\broute\b', r'\bdispatch\b',
                r'\bforward\b', r'\bconnect\b'
            ],
            NodeType.MENU: [
                r'\bmenu\b', r'\boptions\b', r'\bselect\b',
                r'\bchoices\b'
            ],
            NodeType.PROMPT: [
                r'\bplay\b', r'\bspeak\b', r'\bannounce\b',
                r'\bmessage\b'
            ],
            NodeType.ERROR: [
                r'\berror\b', r'\bfail\b', r'\binvalid\b',
                r'\bretry\b', r'\btimeout\b'
            ]
        }

        # Patterns for edges
        # The parser tries to match connections like A --> B or A --|label|--> B
        self.edge_patterns = {
            r'--\>|-{2,}>': '',   # Basic arrow
            r'--\|(.*?)\|->': 'label',  # Labeled edge
            r'-\.->': 'optional', # Dotted arrow
            r'==+>': 'primary'    # Thick arrow
        }

    def parse(self, mermaid_text: str) -> Dict:
        """
        Parse Mermaid diagram text into a structured format.

        Args:
            mermaid_text: Raw Mermaid diagram text.

        Returns:
            A dictionary with 'nodes', 'edges', 'subgraphs', and 'metadata' keys.
        """
        lines = [line.strip() for line in mermaid_text.split('\n') if line.strip()]

        nodes = {}
        edges = []
        subgraphs = {}
        metadata = {
            'title': None,
            'direction': 'TD',
            'styles': {}
        }

        current_subgraph = None

        try:
            for line in lines:
                # Skip comments and directives
                if line.startswith('%%') or line.startswith('%'):
                    continue

                # Parse flowchart direction
                if line.startswith('flowchart') or line.startswith('graph'):
                    direction_match = re.match(r'(?:flowchart|graph)\s+(\w+)', line)
                    if direction_match:
                        metadata['direction'] = direction_match.group(1)
                    continue

                # Handle subgraphs
                if line.startswith('subgraph'):
                    subgraph_match = re.match(r'subgraph\s+(\w+)(?:\s*\[(.*?)\])?', line)
                    if subgraph_match:
                        current_subgraph = subgraph_match.group(1)
                        title = subgraph_match.group(2) or current_subgraph
                        subgraphs[current_subgraph] = {
                            'id': current_subgraph,
                            'title': title,
                            'nodes': set()
                        }
                    continue

                if line == 'end':
                    current_subgraph = None
                    continue

                # Parse nodes
                node_match = self._parse_node(line)
                if node_match:
                    node_id, node = node_match
                    nodes[node_id] = node
                    if current_subgraph:
                        subgraphs[current_subgraph]['nodes'].add(node_id)
                    continue

                # Parse edges
                edge_obj = self._parse_edge(line)
                if edge_obj:
                    edges.append(edge_obj)
                    continue

                # Parse styles
                style_match = self._parse_style(line)
                if style_match:
                    class_name, styles = style_match
                    metadata['styles'][class_name] = styles

            return {
                'nodes': nodes,
                'edges': edges,
                'subgraphs': subgraphs,
                'metadata': metadata
            }

        except Exception as e:
            raise ValueError(f"Failed to parse Mermaid diagram: {str(e)}")

    def _parse_node(self, line: str) -> Optional[tuple]:
        """Parse node definition from a single Mermaid line."""
        # Possible node definition syntaxes: A["text"], A{"text"}, A("text"), etc.
        node_patterns = [
            r'^(\w+)\s*\["([^"]+)"\]',
            r'^(\w+)\s*\{"([^"]+)"\}',
            r'^(\w+)\s*\("([^"]+)"\)',
            r'^(\w+)\s*\[\("([^"]+)"\)\]'
        ]

        for pattern in node_patterns:
            match = re.match(pattern, line)
            if match:
                node_id, text = match.groups()
                node_type = self._determine_node_type(text)
                return node_id, Node(
                    id=node_id,
                    raw_text=text,
                    node_type=node_type
                )
        return None

    def _parse_edge(self, line: str) -> Optional[Edge]:
        """Parse edge definition from a single Mermaid line."""
        for pattern, style in self.edge_patterns.items():
            # We look for something like: A --> B or A --|label|--> B
            # We'll do a multi-phase check: first see if there's a label group, then fallback.
            # This might not capture everything in a single pass, but it's a start.
            labeled_pattern = fr'^(\w+)\s*{pattern}\s*(\w+)'
            match = re.search(labeled_pattern, line)
            if match:
                from_id = match.group(1)
                to_id = match.group(match.lastindex)  # last group is always the to_id
                label = None
                if style == 'label':
                    # If there's a capturing group for the label (.*?) inside the pattern
                    label_match = re.search(r'--\|(.*?)\|->', line)
                    if label_match:
                        label = label_match.group(1).strip()
                return Edge(
                    from_id=from_id,
                    to_id=to_id,
                    label=label,
                    style=style
                )
        return None

    def _parse_style(self, line: str) -> Optional[tuple]:
        """Parse Mermaid style definition."""
        style_match = re.match(r'classDef\s+(\w+)\s+(.*?)$', line)
        if style_match:
            class_name, styles = style_match.groups()
            return class_name, styles
        return None

    def _determine_node_type(self, text: str) -> NodeType:
        """Heuristics for determining the node type based on text content."""
        text_lower = text.lower()

        for node_type, patterns in self.node_patterns.items():
            if any(re.search(pattern, text_lower) for pattern in patterns):
                return node_type

        # Default fallback
        return NodeType.ACTION


def parse_mermaid(mermaid_text: str) -> Dict:
    """
    Convenience wrapper for parsing Mermaid diagrams.

    Args:
        mermaid_text (str): The raw Mermaid diagram text.

    Returns:
        dict: Parsed structure with 'nodes', 'edges', 'subgraphs', and 'metadata'.
    """
    parser = MermaidParser()
    return parser.parse(mermaid_text)
