
import streamlit as st
from google import genai
from pypdf import PdfReader
import docx
import tempfile
import os
import json
import re

# ====================== SYSTEM PROMPT ======================
SYSTEM_PROMPT = """
You are Text2Quiz AI, an expert educational agent.
Rules:
1. Use ONLY the provided source material. Never invent facts.
2. Respect the requested question types and difficulty.
3. Avoid unnecessary repetition.
4. Always return clean valid JSON when asked for a question.
"""

# ====================== HELPERS ======================
def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    try:
        if uploaded_file.name.lower().endswith(".pdf"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            reader = PdfReader(tmp_path)
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            os.unlink(tmp_path)
            return text
        elif uploaded_file.name.lower().endswith(".docx"):
            doc = docx.Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        else:
            return uploaded_file.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"Error reading file: {str(e)}"

def call_gemini(prompt):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"ERROR: {str(e)}"

def parse_json(text):
    try:
        # Clean common markdown
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except Exception as e:
        return None

# ====================== SESSION STATE ======================
defaults = {
    "source_text": "",
    "quiz_started": False,
    "analysis_done": False,
    "analysis_result": "",
    "mode": "practice",
    "question_types": ["multiple_choice"],
    "num_questions": 10,
    "difficulty": "Mixed (recommended)",
    "questions": [],
    "current_index": 0,
    "user_answers": {},
    "finished": False,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ====================== PAGE ======================
st.set_page_config(page_title="Text2Quiz AI", page_icon="📝", layout="centered")
st.title("Text2Quiz AI")
st.caption("For students and teachers")

# ====================== 1. LOAD MATERIAL ======================
if not st.session_state.source_text:
    st.header("Step 1 – Load your material")
    text_input = st.text_area("Paste text here", height=150)
    uploaded_file = st.file_uploader("Or upload PDF / Word", type=["pdf", "docx", "txt"])

    if st.button("Load Material", type="primary"):
        source = text_input.strip() if text_input else ""
        if uploaded_file:
            file_text = extract_text_from_file(uploaded_file)
            if file_text.startswith("Error"):
