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
2. Respect the requested question types, difficulty and number of questions.
3. Avoid unnecessary repetition.
4. Return clean valid JSON when generating questions.
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
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except:
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
    "questions": [],          # list of all generated questions
    "current_index": 0,       # which question we are on
    "user_answers": {},       # index → answer
    "score": 0,
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
                st.error(file_text)
            else:
                source = (source + "\n\n" + file_text) if source else file_text

        if len(source) < 60:
            st.warning("Please provide more content.")
        else:
            st.session_state.source_text = source[:35000]
            st.success("Material loaded!")
            st.rerun()

# ====================== 2. CHOOSE ACTION ======================
if st.session_state.source_text and not st.session_state.quiz_started and not st.session_state.analysis_done:
    st.header("Step 2 – What do you want to do?")

    action = st.radio(
        "Choose an action:",
        [
            "Interactive Quiz (Practice or Exam)",
            "Extract main concepts + explanation",
            "Create a clear summary",
            "Explain the material in simple language"
        ]
    )

    if action == "Interactive Quiz (Practice or Exam)":
        st.subheader("Quiz Settings")

        col1, col2 = st.columns(2)
        with col1:
            mode_choice = st.radio("Mode", ["Practice (feedback after each question)", "Exam (feedback only at the end)"])
            st.session_state.num_questions = st.slider("Number of questions", 5, 40, 10)
        with col2:
            st.session_state.difficulty = st.selectbox(
                "Difficulty",
                ["Easy", "Intermediate", "Difficult", "Mixed (recommended)"]
            )

        st.write("**Question types** (select one or more):")
        selected_types = st.multiselect(
            "Types",
            ["Multiple Choice", "True / False", "Fill in the Blank", "Short Answer", "Matching", "Sequencing"],
            default=["Multiple Choice", "True / False"]
        )

        type_map = {
            "Multiple Choice": "multiple_choice",
            "True / False": "true_false",
            "Fill in the Blank": "fill_blank",
            "Short Answer": "short_answer",
            "Matching": "matching",
            "Sequencing": "sequencing"
        }
        st.session_state.question_types = [type_map[t] for t in selected_types] if selected_types else ["multiple_choice"]

        if st.button("Start Interactive Quiz", type="primary"):
            st.session_state.mode = "practice" if "Practice" in mode_choice else "exam"
            st.session_state.quiz_started = True
            st.session_state.finished = False
            st.session_state.questions = []
            st.session_state.current_index = 0
            st.session_state.user_answers = {}
