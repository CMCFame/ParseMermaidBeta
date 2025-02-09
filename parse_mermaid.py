"""
Enhanced Mermaid parser with IVR-specific functionality
"""
import re
from enum import Enum, auto
from typing import Dict, List, Optional, Union, Set
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
    MENU = auto()        # New: For menu options
    PROMPT = auto()      # New: For voice prompts
    ERROR = auto()       # New: For error handling
    RETRY = auto()       # New: For retry logic

@dataclass
class Node:
    """Enhanced node representation"""
    id: str
    raw_text: str
    node_type: NodeType
    style_classes: List[str] = field(default_factory=list)
    subgraph: Optional[str] = None
    properties: Dict[str, str] = field(default_factory=dict)
    
    def is_interactive(self) -> bool:
        """Check if node requires user interaction"""
        return self.node_type in {NodeType.INPUT, NodeType.MENU, NodeType.DECISION}

@dataclass
class Edge:
    """Enhanced edge representation"""
    from_id: str
    to_id: str
    label: Optional[str] = None
    style: Optional[str] = None
    condition: Optional[str] = None  # New: For conditional flows

class MermaidParser:
    """Enhanced Mermaid parser with IVR focus"""
    
    def __init__(self):
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

        self.edge_patterns = {
            # Standard connection
            r'-->': '',
            # Labeled connection with possible DTMF
            r'--\|(.*?)\|->': 'label',
            # Dotted connection for optional flows
            r'-\.->\s*': 'optional',
            # Thick connection for primary paths
            r'==+>': 'primary'
        }

    def parse(self, mermaid_text: str) -> Dict:
        """
        Parse Mermaid diagram text into structured format
        
        Args:
            mermaid_text: Raw Mermaid diagram text
            
        Returns:
            Dict containing parsed nodes, edges, and metadata
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
                edge = self._parse_edge(line)
                if edge:
                    edges.append(edge)
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
        """Parse node definition"""
        # Match node patterns with various syntax forms
        node_patterns = [
            # ["text"] form
            r'^\s*(\w+)\s*\["([^"]+)"\]',
            # {"text"} form for decisions
            r'^\s*(\w+)\s*\{"([^"]+)"\}',
            # ("text") form
            r'^\s*(\w+)\s*\("([^"]+)"\)',
            # [("text")] form
            r'^\s*(\w+)\s*\[\("([^"]+)"\)\]'
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
        """Parse edge definition"""
        for pattern, style in self.edge_patterns.items():
            match = re.search(f'(\w+)\s*{pattern}\s*(\w+)', line)
            if match:
                from_id, to_id = match.groups()
                label = None
                if 'label' in style and len(match.groups()) > 2:
                    label = match.group(2)
                return Edge(
                    from_id=from_id,
                    to_id=to_id,
                    label=label,
                    style=style
                )
        return None

    def _parse_style(self, line: str) -> Optional[tuple]:
        """Parse style definition"""
        style_match = re.match(r'classDef\s+(\w+)\s+(.*?)$', line)
        if style_match:
            class_name, styles = style_match.groups()
            return class_name, styles
        return None

    def _determine_node_type(self, text: str) -> NodeType:
        """Determine node type from text content"""
        text_lower = text.lower()
        
        for node_type, patterns in self.node_patterns.items():
            if any(re.search(pattern, text_lower) for pattern in patterns):
                return node_type
        
        return NodeType.ACTION

def parse_mermaid(mermaid_text: str) -> Dict:
    """Convenience wrapper for parsing Mermaid diagrams"""
    parser = MermaidParser()
    return parser.parse(mermaid_text)