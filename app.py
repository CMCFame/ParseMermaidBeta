"""
app.py

A refactored Streamlit application with tabs, improved UI, 
and a more accurate 1-to-1 approach for converting Mermaid flowcharts into IVR code.

Usage:
    streamlit run app.py
"""

import streamlit as st
import streamlit_mermaid as st_mermaid
import tempfile
import os
import json
import yaml
from PIL import Image
from typing import Optional

# Local imports
from parse_mermaid import parse_mermaid
from openai_converter import process_flow_diagram
from openai_ivr_converter import convert_mermaid_to_ivr, structured_nodes_to_ivr

# ---------------------------------------------------------
# Constants & Examples
# ---------------------------------------------------------
DEFAULT_FLOWS = {
    "Simple Callout": '''flowchart TD
    A["Welcome<br/>Press 1 if employee<br/>Press 3 for more time<br/>Press 7 if not home<br/>Press 9 to repeat"] --> B{"1 - this is employee"}
    A -->|"no input"| C["30-second message"]
    A -->|"7 - not home"| D["Employee Not Home"]
    A -->|"3 - more time"| C
    A -->|"retry"| A
    B -->|"yes"| E["Enter PIN"]''',

    "PIN Change": '''flowchart TD
    A["Enter PIN"] --> B{"Valid PIN?"}
    B -->|"No"| C["Invalid Entry"]
    B -->|"Yes"| D["PIN Changed"]
    C --> A''',
}

# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------
def validate_mermaid_syntax(mermaid_text: str) -> Optional[str]:
    """
    Validate mermaid syntax by attempting to parse it.
    Returns an error message if invalid, or None if valid.
    """
    try:
        _ = parse_mermaid(mermaid_text)
        return None
    except Exception as e:
        return f"Mermaid parsing error: {str(e)}"


def format_ivr_code(ivr_code: str, export_format: str) -> str:
    """
    Convert the 'module.exports = [ ... ];' code into JSON or YAML if requested.
    Otherwise, leave it as JavaScript.
    """
    if export_format.lower() == "javascript":
        return ivr_code

    # Extract JSON array from `module.exports = [ ... ];`
    try:
        arr_str = ivr_code[len("module.exports = "):].strip()
        if arr_str.endswith(";"):
            arr_str = arr_str[:-1]
        data = json.loads(arr_str)

        if export_format.lower() == "json":
            return json.dumps(data, indent=2)
        elif export_format.lower() == "yaml":
            return yaml.dump(data, allow_unicode=True)
        else:
            raise ValueError(f"Unsupported format: {export_format}")
    except Exception as e:
        return f"Error converting code to {export_format}: {str(e)}"


def render_mermaid_safely(mermaid_text: str):
    """
    Render Mermaid diagram in Streamlit. If error occurs, display fallback.
    """
    try:
        st_mermaid.st_mermaid(mermaid_text, height=400)
    except Exception as e:
        st.error(f"Preview Error: {str(e)}")
        st.code(mermaid_text, language="mermaid")


def save_temp_file(content: str, suffix: str = '.js') -> str:
    """Save content to a temporary file and return the path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
        f.write(content)
        return f.name


# ---------------------------------------------------------
# Main Streamlit App
# ---------------------------------------------------------
def main():
    st.title("Mermaid-to-IVR Converter (Refined)")
    st.markdown("""
    This application allows you to upload or create Mermaid diagrams and convert them
    into a 1-to-1 IVR JavaScript configuration. 
    """)
    
    # --- Initialize session state ---
    if "mermaid_code" not in st.session_state:
        st.session_state["mermaid_code"] = ""
    if "parsed_data" not in st.session_state:
        st.session_state["parsed_data"] = None
    if "ivr_code" not in st.session_state:
        st.session_state["ivr_code"] = ""

    # Retrieve API Key (either from secrets or user input)
    st.sidebar.title("Configuration")
    openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", help="Required for conversions")

    export_format = st.sidebar.selectbox("Export Format", ["JavaScript", "JSON", "YAML"])
    validate_syntax = st.sidebar.checkbox("Validate Diagram", value=True)
    show_debug = st.sidebar.checkbox("Show Debug Info", value=False)

    # Use tabs for a clearer multi-step process
    tab1, tab2 = st.tabs(["Flowchart Input", "Convert to IVR"])

    with tab1:
        st.subheader("1) Provide a Mermaid Diagram or Upload an Image/PDF")

        colA, colB = st.columns(2)
        with colA:
            selected_example = st.selectbox("Load Example Flow", ["Custom"] + list(DEFAULT_FLOWS.keys()))
            if selected_example != "Custom":
                st.session_state["mermaid_code"] = DEFAULT_FLOWS[selected_example]

            st.session_state["mermaid_code"] = st.text_area(
                "Mermaid Diagram Editor",
                st.session_state["mermaid_code"],
                height=300
            )

            # Validate or parse the current Mermaid code
            if st.button("Validate/Parse Mermaid"):
                if validate_syntax:
                    error = validate_mermaid_syntax(st.session_state["mermaid_code"])
                    if error:
                        st.error(error)
                    else:
                        st.success("Mermaid diagram appears valid.")
                        parsed = parse_mermaid(st.session_state["mermaid_code"])
                        st.session_state["parsed_data"] = parsed
                else:
                    st.warning("Validation is disabled in sidebar.")
        
        with colB:
            # Optionally upload an image to convert to Mermaid
            uploaded_file = st.file_uploader("Upload Diagram (pdf/png/jpg/jpeg)")
            if uploaded_file and openai_api_key:
                if st.button("Convert Image/PDF to Mermaid"):
                    with st.spinner("Converting..."):
                        try:
                            suffix = os.path.splitext(uploaded_file.name)[1]
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                tmp_file_path = tmp_file.name

                            # Convert to Mermaid
                            mermaid_text = process_flow_diagram(tmp_file_path, api_key=openai_api_key)
                            os.unlink(tmp_file_path)

                            st.session_state["mermaid_code"] = mermaid_text
                            st.success("Image converted to Mermaid successfully!")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

            # Preview
            if st.session_state["mermaid_code"]:
                st.write("**Mermaid Preview:**")
                render_mermaid_safely(st.session_state["mermaid_code"])

    with tab2:
        st.subheader("2) Convert Parsed Data to IVR Code")

        # Attempt to parse if not parsed yet
        if st.session_state["mermaid_code"] and not st.session_state["parsed_data"]:
            # In case user didn't hit 'Validate/Parse' in tab1
            if validate_syntax:
                error = validate_mermaid_syntax(st.session_state["mermaid_code"])
                if error:
                    st.error(error)
                else:
                    st.session_state["parsed_data"] = parse_mermaid(st.session_state["mermaid_code"])
            else:
                st.session_state["parsed_data"] = parse_mermaid(st.session_state["mermaid_code"])

        if st.session_state["parsed_data"] is None:
            st.info("Please provide/parse a Mermaid diagram first in Tab 1.")
        else:
            # Button to convert the parsed data to IVR
            if st.button("Convert to IVR"):
                if not openai_api_key:
                    st.error("Please provide an OpenAI API key.")
                else:
                    with st.spinner("Generating IVR code..."):
                        try:
                            # Option A: 1-to-1 structured approach
                            ivr_js_code = structured_nodes_to_ivr(st.session_state["parsed_data"], openai_api_key)
                            st.session_state["ivr_code"] = ivr_js_code

                            st.success("Conversion to IVR successful!")
                        except Exception as e:
                            st.error(f"Conversion error: {str(e)}")
                            if show_debug:
                                st.exception(e)

            # Display the generated code side-by-side with the Mermaid preview
            if st.session_state["ivr_code"]:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Mermaid Diagram")
                    render_mermaid_safely(st.session_state["mermaid_code"])

                with col2:
                    st.subheader("Generated IVR Code")
                    formatted_code = format_ivr_code(st.session_state["ivr_code"], export_format)
                    st.code(formatted_code, language=export_format.lower())

                    # Download button
                    tmp_file = save_temp_file(formatted_code, suffix={
                        "JavaScript": ".js",
                        "JSON": ".json",
                        "YAML": ".yaml"
                    }.get(export_format, ".js"))

                    with open(tmp_file, 'rb') as f:
                        st.download_button(
                            label="Download IVR Config",
                            data=f,
                            file_name=f"ivr_flow.{export_format.lower()}",
                            mime="text/plain"
                        )
                    os.unlink(tmp_file)

        # Debug info
        if show_debug and st.session_state["parsed_data"]:
            with st.expander("Debug: Parsed Data"):
                st.json(st.session_state["parsed_data"])

            if st.session_state["ivr_code"]:
                with st.expander("Debug: Raw IVR Code"):
                    st.code(st.session_state["ivr_code"], language="javascript")


if __name__ == "__main__":
    main()
