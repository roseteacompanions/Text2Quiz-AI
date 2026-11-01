import streamlit as st
import os
from google import genai
from pypdf import PdfReader
import docx
import tempfile

# ========== SYSTEM PROMPT ==========
SYSTEM_PROMPT = """You are Text2Quiz AI, an educational content analysis and quiz-generation agent.
Your job is to read and understand educational or informational content provided by the user, identify the important concepts, and create high-quality quizzes that test those concepts without unnecessary repetition.

Follow all the rules previously defined for analysis, concept mapping, question types, no-repetition, difficulty levels, and output format.
Never invent facts. Only use information from the source.
"""

def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    try:
        if uploaded_file.name.endswith(".pdf"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            reader = PdfReader(tmp_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            os.unlink(tmp_path)
            return text
        elif uploaded_file.name.endswith(".docx"):
            doc = docx.Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        else:
            return str(uploaded_file.read(), "utf-8", errors="ignore")
    except Exception as e:
        return f"Error reading file: {str(e)}"

def call_gemini(prompt):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        return "ERROR: GEMINI_API_KEY not found in secrets. Please check your Streamlit Secrets."

    try:
        client = genai.Client(api_key=api_key)
        
        # Using a reliable free model
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{SYSTEM_PROMPT}\n\n---\n\nUser request:\n{prompt}"
        )
        return response.text
    except Exception as e:
        return f"ERROR calling Gemini:\n{str(e)}"

# ========== INTERFACE ==========
st.set_page_config(page_title="Text2Quiz AI", page_icon="📝", layout="wide")

st.title("Text2Quiz AI")
st.write("Free educational quiz generator for students and teachers")

text_input = st.text_area("Paste your text here", height=200)
uploaded_file = st.file_uploader("Or upload a file (PDF / Word)", type=["pdf", "docx", "txt"])

mode = st.radio("What do you want?", ["Make a quiz", "Analyze this"], horizontal=True)

if st.button("Generate", type="primary"):
    source = text_input.strip() if text_input else ""
    
    if uploaded_file is not None:
        file_text = extract_text_from_file(uploaded_file)
        if file_text.startswith("Error"):
            st.error(file_text)
            st.stop()
        source = (source + "\n\n" + file_text) if source else file_text

    if not source:
        st.warning("Please paste some text or upload a document first.")
    else:
        with st.spinner("Working... please wait 15-40 seconds"):
            if mode == "Analyze this":
                user_request = f"Analyze this content carefully and create a concept map:\n\n{source[:15000]}"
            else:
                user_request = f"Make a balanced quiz from this content. Include different question types and an Answer Key:\n\n{source[:15000]}"
            
            result = call_gemini(user_request)
            st.markdown(result)
