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
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
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
                st.error(file_text)
            else:
                source = (source + "\n\n" + file_text) if source else file_text

        if len(source) < 50:
            st.warning("Please provide more content.")
        else:
            st.session_state.source_text = source[:35000]
            st.success("Material loaded successfully!")
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
            st.session_state.num_questions = st.slider("Number of questions", 5, 30, 8)
        with col2:
            st.session_state.difficulty = st.selectbox(
                "Difficulty",
                ["Easy", "Intermediate", "Difficult", "Mixed (recommended)"]
            )

        st.write("**Question types** (you can choose several):")
        selected_types = st.multiselect(
            "Select types",
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
            st.rerun()

    else:
        if st.button("Generate", type="primary"):
            with st.spinner("Working..."):
                if "concepts" in action.lower():
                    prompt = f"{SYSTEM_PROMPT}\n\nExtract the main concepts and give a clear short explanation for each.\n\nMATERIAL:\n{st.session_state.source_text}"
                elif "summary" in action.lower():
                    prompt = f"{SYSTEM_PROMPT}\n\nWrite a clear structured summary suitable for students.\n\nMATERIAL:\n{st.session_state.source_text}"
                else:
                    prompt = f"{SYSTEM_PROMPT}\n\nExplain the material in simple language for a student.\n\nMATERIAL:\n{st.session_state.source_text}"

                result = call_gemini(prompt)
                st.session_state.analysis_result = result
                st.session_state.analysis_done = True
                st.rerun()

# ====================== ANALYSIS RESULT ======================
if st.session_state.analysis_done:
    st.header("Result")
    st.markdown(st.session_state.analysis_result)
    if st.button("← Back to menu"):
        st.session_state.analysis_done = False
        st.session_state.analysis_result = ""
        st.rerun()

# ====================== GENERATE QUESTION ======================
def generate_question():
    history = [q.get("concept", "") for q in st.session_state.questions if q.get("concept")]
    history_text = "\n".join([f"- {h}" for h in history[-8:]]) if history else "None"

    prompt = f"""
{SYSTEM_PROMPT}

SOURCE MATERIAL:
\"\"\"
{st.session_state.source_text[:12000]}
\"\"\"

Previously used concepts (do not repeat the same way):
{history_text}

Create ONE question.
Allowed types: {', '.join(st.session_state.question_types)}
Difficulty: {st.session_state.difficulty}

Return ONLY a valid JSON object in this exact format:

{{
  "type": "multiple_choice",
  "question": "Clear question here",
  "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
  "correct": "B",
  "explanation": "Short explanation",
  "concept": "short concept name"
}}

Rules:
- true_false → options: ["True", "False"]
- fill_blank or short_answer → options: []
- matching → put items in options
- sequencing → put steps in options
"""
    raw = call_gemini(prompt)
    data = parse_json(raw)
    return data, raw

# ====================== QUIZ ======================
if st.session_state.quiz_started and not st.session_state.finished:

    # Generate first question if needed
    if len(st.session_state.questions) == 0:
        with st.spinner("Generating the first question... please wait"):
            qdata, raw = generate_question()
            if qdata is None:
                st.error("Failed to generate the first question.")
                st.code(raw)
                if st.button("Try again"):
                    st.rerun()
                st.stop()
            st.session_state.questions.append(qdata)
            st.rerun()

    # Generate next question when needed
    if (st.session_state.current_index >= len(st.session_state.questions) and 
        len(st.session_state.questions) < st.session_state.num_questions):
        with st.spinner("Generating next question..."):
            qdata, raw = generate_question()
            if qdata is None:
                st.warning("Could not generate more questions.")
                st.session_state.finished = True
                st.rerun()
            else:
                st.session_state.questions.append(qdata)
                st.rerun()

    if st.session_state.current_index >= len(st.session_state.questions):
        st.session_state.finished = True
        st.rerun()

    idx = st.session_state.current_index
    q = st.session_state.questions[idx]

    st.markdown(f"### Question {idx + 1} of {st.session_state.num_questions}")
    st.caption(f"Type: {q.get('type', '').replace('_', ' ').title()} | Mode: {st.session_state.mode.title()}")
    st.write(q.get("question", "No question text"))
    st.write("")

    # Answer slot
    qtype = q.get("type", "multiple_choice")
    current_answer = st.session_state.user_answers.get(idx)

    if qtype == "multiple_choice":
        options = q.get("options", [])
        answer = st.radio("Select your answer:", options, key=f"r_{idx}")
    elif qtype == "true_false":
        answer = st.radio("Select your answer:", ["True", "False"], key=f"tf_{idx}")
    elif qtype in ["fill_blank", "short_answer"]:
        answer = st.text_input("Type your answer:", value=current_answer or "", key=f"t_{idx}")
    elif qtype == "matching":
        st.info("Matching question")
        for opt in q.get("options", []):
            st.write(f"• {opt}")
        answer = st.text_area("Write the correct matches:", value=current_answer or "", key=f"m_{idx}")
    elif qtype == "sequencing":
        st.info("Put the steps in the correct order")
        for i, opt in enumerate(q.get("options", []), 1):
            st.write(f"{i}. {opt}")
        answer = st.text_input("Correct order (example: 2,1,4,3):", value=current_answer or "", key=f"s_{idx}")
    else:
        answer = st.text_input("Your answer:", value=current_answer or "", key=f"o_{idx}")

    if answer is not None:
        st.session_state.user_answers[idx] = answer

    st.write("")

    # Navigation
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("← Previous", disabled=(idx == 0)):
            st.session_state.current_index = max(0, idx - 1)
            st.rerun()

    with col2:
        if st.button("Next →"):
            if idx < st.session_state.num_questions - 1:
                st.session_state.current_index = idx + 1
                st.rerun()
            else:
                st.session_state.finished = True
                st.rerun()

    with col3:
        if st.session_state.mode == "practice" and st.button("Check Answer"):
            correct = str(q.get("correct", "")).strip().lower()
            given = str(st.session_state.user_answers.get(idx, "")).strip().lower()
            if qtype == "multiple_choice" and ")" in given:
                given = given.split(")")[0].strip().lower()

            if correct in given or given in correct or given == correct:
                st.success("Correct!\n\n" + str(q.get("explanation", "")))
            else:
                st.error(f"Incorrect.\nCorrect answer: {q.get('correct')}\n\n{q.get('explanation', '')}")

    with col4:
        if st.button("Finish Quiz", type="primary"):
            st.session_state.finished = True
            st.rerun()

# ====================== RESULTS ======================
if st.session_state.finished:
    st.header("Final Results")

    total = len(st.session_state.questions)
    score = 0
    wrong_concepts = []

    for i, q in enumerate(st.session_state.questions):
        given = str(st.session_state.user_answers.get(i, "")).strip().lower()
        correct = str(q.get("correct", "")).strip().lower()
        if q.get("type") == "multiple_choice" and ")" in given:
            given = given.split(")")[0].strip().lower()

        is_correct = correct in given or given in correct or given == correct
        if is_correct:
            score += 1
        elif q.get("concept"):
            wrong_concepts.append(q["concept"])

    percent = round(score / total * 100) if total > 0 else 0
    st.metric("Score", f"{score} / {total} ({percent}%)")

    if percent >= 85:
        st.success("Excellent work!")
    elif percent >= 70:
        st.info("Good result.")
    elif percent >= 50:
        st.warning("Some important concepts need more practice.")
    else:
        st.error("Please review the main concepts and try again.")

    if wrong_concepts:
        st.subheader("Where to improve")
        for c in sorted(set(wrong_concepts)):
            st.write(f"• {c}")

    with st.expander("Review all questions"):
        for i, q in enumerate(st.session_state.questions):
            st.markdown(f"**Q{i+1}:** {q.get('question')}")
            st.write(f"Your answer: {st.session_state.user_answers.get(i, '—')}")
            st.write(f"Correct: {q.get('correct')}")
            if q.get("explanation"):
                st.write(q["explanation"])
            st.divider()

    if st.button("← Back to main menu"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
