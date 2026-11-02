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
2. When creating questions, respect the requested question types, difficulty, and number.
3. Avoid unnecessary repetition of the same concept.
4. Always return clean, valid JSON when asked for questions.
5. For analysis/summary modes, be clear, structured and useful for students and teachers.
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
    "difficulty": "mixed",
    "current_question_data": None,
    "feedback": None,
    "score": 0,
    "total_answered": 0,
    "history": [],
    "answers_log": [],
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

# ====================== 2. CHOOSE WHAT TO DO ======================
if st.session_state.source_text and not st.session_state.quiz_started and not st.session_state.analysis_done:
    st.header("Step 2 – What do you want to do?")

    action = st.radio(
        "Choose an action:",
        [
            "Interactive Quiz (Practice or Exam)",
            "Extract main concepts + explanation",
            "Create a clear summary of the material",
            "Explain the material in simple language"
        ]
    )

    if action == "Interactive Quiz (Practice or Exam)":
        st.subheader("Quiz Settings")

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.mode = st.radio("Mode", ["Practice (feedback after each question)", "Exam (feedback only at the end)"])
            st.session_state.num_questions = st.slider("Number of questions", 5, 50, 10)

        with col2:
            st.session_state.difficulty = st.selectbox(
                "Difficulty",
                ["Easy", "Intermediate", "Difficult", "Mixed (recommended)"]
            )

        st.write("**Question types** (you can select several):")
        types = st.multiselect(
            "Select the types you want:",
            [
                "Multiple Choice",
                "True / False",
                "Fill in the Blank",
                "Short Answer",
                "Matching",
                "Sequencing"
            ],
            default=["Multiple Choice", "True / False"]
        )

        # Convert to internal names
        type_map = {
            "Multiple Choice": "multiple_choice",
            "True / False": "true_false",
            "Fill in the Blank": "fill_blank",
            "Short Answer": "short_answer",
            "Matching": "matching",
            "Sequencing": "sequencing"
        }
        st.session_state.question_types = [type_map[t] for t in types] if types else ["multiple_choice"]

        if st.button("Start Interactive Quiz", type="primary"):
            st.session_state.mode = "practice" if "Practice" in st.session_state.mode else "exam"
            st.session_state.quiz_started = True
            st.session_state.finished = False
            st.session_state.score = 0
            st.session_state.total_answered = 0
            st.session_state.history = []
            st.session_state.answers_log = []
            st.session_state.current_question_data = None
            st.session_state.feedback = None
            st.rerun()

    else:
        # Analysis / Summary / Explanation modes
        if st.button("Generate", type="primary"):
            with st.spinner("Working..."):
                if "concepts" in action.lower():
                    prompt = f"{SYSTEM_PROMPT}\n\nExtract the main concepts from the material below and give a clear short explanation for each concept.\n\nMATERIAL:\n{st.session_state.source_text}"
                elif "summary" in action.lower():
                    prompt = f"{SYSTEM_PROMPT}\n\nWrite a clear, well-structured summary of the material below, suitable for students.\n\nMATERIAL:\n{st.session_state.source_text}"
                else:
                    prompt = f"{SYSTEM_PROMPT}\n\nExplain the material below in simple language so a student can easily understand it.\n\nMATERIAL:\n{st.session_state.source_text}"

                result = call_gemini(prompt)
                st.session_state.analysis_result = result
                st.session_state.analysis_done = True
                st.rerun()

# ====================== SHOW ANALYSIS RESULT ======================
if st.session_state.analysis_done:
    st.header("Result")
    st.markdown(st.session_state.analysis_result)
    if st.button("Back to menu"):
        st.session_state.analysis_done = False
        st.session_state.analysis_result = ""
        st.rerun()

# ====================== GENERATE ONE QUESTION ======================
def generate_next_question():
    history_text = ""
    if st.session_state.history:
        history_text = "Previously used concepts (avoid repeating the same way):\n" + "\n".join([f"- {h}" for h in st.session_state.history[-12:]])

    types_str = ", ".join(st.session_state.question_types)
    diff = st.session_state.difficulty

    prompt = f"""
{SYSTEM_PROMPT}

SOURCE MATERIAL:
\"\"\"
{st.session_state.source_text}
\"\"\"

{history_text}

Create ONE question.
Allowed types: {types_str}
Difficulty: {diff}

Return ONLY valid JSON in this format:

{{
  "type": "multiple_choice",
  "question": "the question",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": "B",
  "explanation": "short explanation",
  "concept": "short concept name"
}}

Rules for special types:
- true_false → options: ["True", "False"]
- fill_blank / short_answer → options: []
- matching → put the pairs in options, correct = the correct matching description
- sequencing → put the steps in options, correct = the correct order
"""

    raw = call_gemini(prompt)
    return parse_json(raw)

# ====================== INTERACTIVE QUIZ ======================
if st.session_state.quiz_started and not st.session_state.finished:

    # Stop when we reach the requested number of questions
    if st.session_state.total_answered >= st.session_state.num_questions:
        st.session_state.finished = True
        st.rerun()

    if st.session_state.current_question_data is None:
        with st.spinner("Generating question..."):
            qdata = generate_next_question()
            if not qdata:
                st.error("Failed to generate question. Try again.")
                st.stop()
            st.session_state.current_question_data = qdata
            st.session_state.feedback = None

    q = st.session_state.current_question_data
    st.markdown(f"### Question {st.session_state.total_answered + 1} of {st.session_state.num_questions}")
    st.caption(f"Type: {q.get('type', '').replace('_', ' ').title()} | Difficulty: {st.session_state.difficulty}")

    st.write(q["question"])

    user_answer = None
