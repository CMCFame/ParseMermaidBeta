"""
Streamlit app for IVR flow conversion with enhanced OpenAI integration
"""
import streamlit as st
import streamlit_mermaid as st_mermaid
import json
import yaml
from typing import Optional, Dict, Any
import tempfile
import os
from PIL import Image
import traceback

from parse_mermaid import parse_mermaid, MermaidParser
from openai_ivr_converter import convert_mermaid_to_ivr
from openai_converter import process_flow_diagram

# Page configuration
st.set_page_config(
    page_title="Mermaid-to-IVR Converter",
    page_icon="🔄",
    layout="wide"
)

# Constants and examples
DEFAULT_FLOWS = {
    "Simple Callout": '''flowchart TD
    A["Welcome<br/>This is an electric callout from (Level 2).<br/>Press 1, if this is (employee).<br/>Press 3, if you need more time to get (employee) to the phone.<br/>Press 7, if (employee) is not home.<br/>Press 9, to repeat this message."] -->|"input"| B{"1 - this is employee"}
    A -->|"no input - go to pg 3"| C["30-second message<br/>Press any key to continue..."]
    A -->|"7 - not home"| D["Employee Not Home"]
    A -->|"3 - need more time"| C
    A -->|"retry logic"| A
    B -->|"yes"| E["Enter Employee PIN"]''',
    
    "PIN Change": '''flowchart TD
    A["Enter PIN"] --> B{"Valid PIN?"}
    B -->|"No"| C["Invalid Entry"]
    B -->|"Yes"| D["PIN Changed"]
    C --> A''',
    
    "Transfer Flow": '''flowchart TD
    A["Transfer Request"] --> B{"Transfer Available?"}
    B -->|"Yes"| C["Connect"]
    B -->|"No"| D["Failed"]
    C --> E["End"]
    D --> E'''
}

def save_temp_file(content: str, suffix: str = '.js') -> str:
    """Save content to a temporary file and return the path"""
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
        f.write(content)
        return f.name

def validate_mermaid(mermaid_text: str) -> Optional[str]:
    """Validate Mermaid diagram syntax"""
    try:
        parser = MermaidParser()
        parser.parse(mermaid_text)
        return None
    except Exception as e:
        return f"Diagram Validation Error: {str(e)}"

def format_ivr_code(ivr_code: str, format_type: str = 'javascript') -> str:
    """Format IVR code according to selected output format"""
    try:
        if format_type == 'javascript':
            return ivr_code
        
        # Extract JSON array from module.exports
        json_str = ivr_code[16:-1].strip()  # Remove "module.exports = " and ";"
        data = json.loads(json_str)
        
        if format_type == 'json':
            return json.dumps(data, indent=2)
        elif format_type == 'yaml':
            return yaml.dump(data, allow_unicode=True)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    except Exception as e:
        st.error(f"Format Error: {str(e)}")
        return ivr_code

def show_code_diff(original: str, converted: str):
    """Show comparison of original and converted code"""
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Original Mermaid")
        st.code(original, language="mermaid")
    with col2:
        st.subheader("Generated IVR Code")
        st.code(converted, language="javascript")

def render_mermaid_safely(mermaid_text: str):
    """Safely render Mermaid diagram with error handling"""
    try:
        st_mermaid.st_mermaid(mermaid_text, height=400)
    except Exception as e:
        st.error(f"Preview Error: {str(e)}")
        st.code(mermaid_text, language="mermaid")

def main():
    st.title("🔄 Mermaid-to-IVR Converter")
    st.markdown("""
    This tool converts flow diagrams into IVR configurations.
    Supports multiple input methods and formats.
    """)

    # Initialize session state
    if 'last_mermaid_code' not in st.session_state:
        st.session_state.last_mermaid_code = None
    if 'last_ivr_code' not in st.session_state:
        st.session_state.last_ivr_code = None

    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Input method selection
        conversion_method = st.radio(
            "Input Method",
            ["Mermaid Editor", "Image Upload"]
        )
        
        # Export format selection
        export_format = st.radio(
            "Export Format",
            ["JavaScript", "JSON", "YAML"]
        )
        
        # Advanced settings
        st.subheader("Advanced Settings")
        validate_syntax = st.checkbox("Validate Diagram", value=True)
        show_debug = st.checkbox("Show Debug Info", value=False)

        # API Configuration
        st.subheader("API Configuration")
        openai_api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="Required for image processing and IVR conversion"
        )

    # Main content area
    if conversion_method == "Mermaid Editor":
        # Example flow selection
        selected_example = st.selectbox(
            "Load Example Flow",
            ["Custom"] + list(DEFAULT_FLOWS.keys())
        )
        
        # Mermaid editor
        if selected_example != "Custom":
            mermaid_text = st.text_area(
                "Mermaid Diagram",
                DEFAULT_FLOWS[selected_example],
                height=400
            )
        else:
            mermaid_text = st.text_area(
                "Mermaid Diagram",
                st.session_state.last_mermaid_code or "",
                height=400
            )

    else:  # Image Upload
        col1, col2 = st.columns(2)
        
        with col1:
            # File uploader
            uploaded_file = st.file_uploader(
                "Upload Flowchart",
                type=['pdf', 'png', 'jpg', 'jpeg']
            )
        
        with col2:
            if uploaded_file:
                try:
                    image = Image.open(uploaded_file)
                    st.image(image, caption="Uploaded Flowchart", use_column_width=True)
                except Exception as e:
                    st.error(f"Error loading image: {str(e)}")
        
        # Convert image to Mermaid
        mermaid_text = ""
        if uploaded_file and openai_api_key:
            if st.button("🔄 Convert Image to Mermaid"):
                with st.spinner("Converting image..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                            tmp_file.write(uploaded_file.getvalue())
                            mermaid_text = process_flow_diagram(tmp_file.name, openai_api_key)
                            st.session_state.last_mermaid_code = mermaid_text
                        
                        st.success("Image converted successfully!")
                        st.subheader("Generated Mermaid Code")
                        st.code(mermaid_text, language="mermaid")
                        
                    except Exception as e:
                        st.error(f"Conversion Error: {str(e)}")
                        if show_debug:
                            st.exception(e)
                    finally:
                        if 'tmp_file' in locals():
                            os.unlink(tmp_file.name)

    # Preview area
    if mermaid_text:
        st.subheader("👁️ Preview")
        render_mermaid_safely(mermaid_text)

    # Convert button
    if st.button("🔄 Convert to IVR"):
        if not openai_api_key:
            st.error("Please provide an OpenAI API key in the sidebar.")
            return

        with st.spinner("Converting to IVR..."):
            try:
                # Validate diagram if requested
                if validate_syntax:
                    error = validate_mermaid(mermaid_text)
                    if error:
                        st.error(error)
                        return

                # Convert to IVR using OpenAI
                ivr_code = convert_mermaid_to_ivr(mermaid_text, openai_api_key)
                st.session_state.last_ivr_code = ivr_code
                
                # Format output
                output = format_ivr_code(ivr_code, export_format.lower())

                # Show result
                st.subheader("📤 Generated IVR Configuration")
                st.code(output, language=export_format.lower())
                
                # Debug information
                if show_debug:
                    with st.expander("Debug Information"):
                        st.text("Original Response:")
                        st.code(ivr_code)
                        st.text("Parsed Nodes:")
                        try:
                            json_str = ivr_code[16:-1].strip()
                            st.json(json.loads(json_str))
                        except Exception as e:
                            st.error(f"Parse Error: {str(e)}")

                # Download option
                tmp_file = save_temp_file(output)
                with open(tmp_file, 'rb') as f:
                    st.download_button(
                        label="⬇️ Download Configuration",
                        data=f,
                        file_name=f"ivr_flow.{export_format.lower()}",
                        mime="text/plain"
                    )
                os.unlink(tmp_file)

                # Show differences
                show_code_diff(mermaid_text, output)

            except Exception as e:
                st.error(f"Conversion Error: {str(e)}")
                if show_debug:
                    st.exception(e)
                    st.text("Traceback:")
                    st.text(traceback.format_exc())

if __name__ == "__main__":
    main()