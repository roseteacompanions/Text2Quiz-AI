import streamlit as st
from google import genai
from pypdf import PdfReader
import docx
import tempfile
import os
import json
import re
import random

# ====================== SYSTEM PROMPT ======================
SYSTEM_PROMPT = """
You are Text2Quiz AI, an expert educational quiz generator.
Strict rules:
1. Use ONLY information from the source material. Never invent facts.
2. Create high-quality questions that test important concepts.
3. Avoid repeating the same concept in the same way.
4. Vary difficulty and reasoning.
5. Always return valid JSON in the exact format requested. No extra text.
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
    "mode": "practice",          # practice or exam
    "current_question_data": None,
    "feedback": None,
    "score": 0,
    "total_answered": 0,
    "history": [],
    "answers_log": [],           # for exam mode review
    "finished": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ====================== PAGE ======================
st.set_page_config(page_title="Text2Quiz AI", page_icon="📝", layout="centered")
st.title("Text2Quiz AI – Stage 2")

# ====================== LOAD MATERIAL ======================
if not st.session_state.quiz_started:
    st.subheader("1. Load your material")
    text_input = st.text_area("Paste text", height=160)
    uploaded_file = st.file_uploader("Or upload PDF / Word", type=["pdf", "docx", "txt"])

    if st.button("Load Material", type="primary"):
        source = text_input.strip() if text_input else ""
        if uploaded_file:
            file_text = extract_text_from_file(uploaded_file)
            if file_text.startswith("Error"):
                st.error(file_text)
            else:
                source = (source + "\n\n" + file_text) if source else file_text

        if len(source) < 80:
            st.warning("Please provide more content.")
        else:
            st.session_state.source_text = source[:30000]
            # reset everything
            for k in ["quiz_started", "current_question_data", "feedback", "finished"]:
                st.session_state[k] = False if k != "source_text" else st.session_state.source_text
            st.session_state.score = 0
            st.session_state.total_answered = 0
            st.session_state.history = []
            st.session_state.answers_log = []
            st.session_state.current_question_data = None
            st.session_state.feedback = None
            st.session_state.finished = False
            st.success("Material loaded successfully!")
            st.rerun()

# ====================== CHOOSE MODE ======================
if st.session_state.source_text and not st.session_state.quiz_started:
    st.success("Material ready.")
    mode = st.radio("Choose mode:", ["Practice Mode (feedback after each question)", "Exam Mode (feedback only at the end)"])
    if st.button("Start Quiz", type="primary"):
        st.session_state.mode = "practice" if "Practice" in mode else "exam"
        st.session_state.quiz_started = True
        st.session_state.finished = False
        st.rerun()

# ====================== GENERATE QUESTION ======================
def generate_next_question():
    history_text = ""
    if st.session_state.history:
        history_text = "Previously tested concepts (avoid repeating the same way):\n"
        for h in st.session_state.history[-10:]:
            history_text += f"- {h}\n"

    # Difficulty progression
    n = st.session_state.total_answered
    if n < 4:
        difficulty = "easy (basic recall)"
    elif n < 9:
        difficulty = "intermediate (understanding + simple application)"
    else:
        difficulty = "difficult (analysis, comparison, or multi-step reasoning)"

    prompt = f"""
{SYSTEM_PROMPT}

SOURCE MATERIAL:
\"\"\"
{st.session_state.source_text}
\"\"\"

{history_text}

Create ONE high-quality question.
Difficulty: {difficulty}
Choose the best type from these options:
- multiple_choice
- true_false
- fill_blank
- short_answer
- matching
- sequencing

Return ONLY this JSON format (no extra text outside the JSON):

{{
  "type": "multiple_choice",
  "question": "Clear question text",
  "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
  "correct": "B",
  "explanation": "Short clear explanation",
  "concept": "short concept name"
}}

Special rules:
- For true_false: options = ["True", "False"], correct = "True" or "False"
- For fill_blank / short_answer: options = [], correct = the expected answer text
- For matching: 
  options = ["Term1 → Definition1", "Term2 → Definition2", ...] (already matched pairs for reference)
  correct = the list of correct pairs as text
  In the question, present the terms and definitions scrambled and ask student to match them.
- For sequencing:
  options = ["Step 1 text", "Step 2 text", "Step 3 text", ...]
  correct = the correct order as numbers or text
"""

    raw = call_gemini(prompt)
    data = parse_json(raw)
    return data

# ====================== QUIZ LOOP ======================
if st.session_state.quiz_started and not st.session_state.finished:

    if st.session_state.current_question_data is None:
        with st.spinner("Generating next question..."):
            qdata = generate_next_question()
            if qdata is None:
                st.error("Could not generate a valid question. Please try again or restart.")
                st.stop()
            st.session_state.current_question_data = qdata
            st.session_state.feedback = None

    q = st.session_state.current_question_data
    st.markdown(f"### Question {st.session_state.total_answered + 1}")
    st.caption(f"Type: {q.get('type', '').replace('_', ' ').title()} | Mode: {st.session_state.mode.title()}")
    st.write(q["question"])

    user_answer = None

    # ---------- INPUT WIDGETS ----------
    qtype = q.get("type", "multiple_choice")

    if qtype == "multiple_choice":
        options = q.get("options", [])
        user_answer = st.radio("Select your answer:", options, key=f"ans_{st.session_state.total_answered}")

    elif qtype == "true_false":
        user_answer = st.radio("Select:", ["True", "False"], key=f"ans_{st.session_state.total_answered}")

    elif qtype in ["fill_blank", "short_answer"]:
        user_answer = st.text_input("Type your answer:", key=f"ans_{st.session_state.total_answered}")

    elif qtype == "matching":
        st.info("Matching question – use the dropdowns to match items.")
        # Simple matching UI with selectboxes
        options = q.get("options", [])
        if options:
            st.write("Possible pairs (for reference):")
            for opt in options:
                st.write(f"- {opt}")
        user_answer = st.text_area("Write your matches (example: Term1 → DefinitionX, Term2 → DefinitionY)", key=f"ans_{st.session_state.total_answered}")

    elif qtype == "sequencing":
        st.info("Sequencing question – put the steps in the correct order.")
        options = q.get("options", [])
        if options:
            st.write("Steps (scrambled):")
            for i, opt in enumerate(options, 1):
                st.write(f"{i}. {opt}")
        user_answer = st.text_input("Write the correct order (example: 3,1,4,2 or the full sequence)", key=f"ans_{st.session_state.total_answered}")

    else:
        user_answer = st.text_input("Your answer:", key=f"ans_{st.session_state.total_answered}")

    # ---------- BUTTONS ----------
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Submit Answer", type="primary"):
            if not user_answer or str(user_answer).strip() == "":
                st.warning("Please provide an answer.")
            else:
                correct = str(q.get("correct", "")).strip().lower()
                given = str(user_answer).strip().lower()

                # Better checking for multiple choice
                if qtype == "multiple_choice" and ")" in given:
                    given_letter = given.split(")")[0].strip().lower()
                    is_correct = given_letter == correct or correct in given
                else:
                    is_correct = correct in given or given in correct or given == correct

                st.session_state.total_answered += 1
                if is_correct:
                    st.session_state.score += 1

                # Save for exam review
                st.session_state.answers_log.append({
                    "question": q["question"],
                    "your_answer": user_answer,
                    "correct": q.get("correct"),
                    "explanation": q.get("explanation", ""),
                    "is_correct": is_correct,
                    "concept": q.get("concept", "")
                })

                st.session_state.history.append(q.get("concept", q["question"][:50]))

                if st.session_state.mode == "practice":
                    if is_correct:
                        st.session_state.feedback = ("correct", q.get("explanation", "Correct!"))
                    else:
                        st.session_state.feedback = ("wrong", f"Incorrect.\n\nCorrect answer: {q.get('correct')}\n\n{q.get('explanation', '')}")
                else:
                    # Exam mode – just move on
                    st.session_state.current_question_data = None
                    st.session_state.feedback = None

                st.rerun()

    with col2:
        if st.button("Next Question"):
            st.session_state.current_question_data = None
            st.session_state.feedback = None
            st.rerun()

    with col3:
        if st.button("Finish & See Results"):
            st.session_state.finished = True
            st.rerun()

    # Show feedback only in Practice mode
    if st.session_state.feedback and st.session_state.mode == "practice":
        kind, msg = st.session_state.feedback
        if kind == "correct":
            st.success(msg)
        else:
            st.error(msg)

# ====================== RESULTS ======================
if st.session_state.finished:
    st.header("Final Results")
    total = st.session_state.total_answered
    score = st.session_state.score

    if total == 0:
        st.write("No questions were answered.")
    else:
        percent = round((score / total) * 100)
        st.metric("Your Score", f"{score} / {total}   ({percent}%)")

        st.subheader("Performance Summary")
        if percent >= 85:
            st.success("Excellent! You have a strong grasp of the material.")
        elif percent >= 70:
            st.info("Good work. A few concepts need more attention.")
        elif percent >= 50:
            st.warning("You understand parts of the material, but significant improvement is needed.")
        else:
            st.error("You need to review the core concepts carefully and try again.")

        # Show where to improve
        st.subheader("Where to improve")
        wrong_concepts = [a["concept"] for a in st.session_state.answers_log if not a["is_correct"] and a["concept"]]
        if wrong_concepts:
            st.write("Focus on these concepts:")
            for c in set(wrong_concepts):
                st.write(f"- {c}")
        else:
            st.write("Great job — almost no weak areas detected!")

        # Detailed review (especially useful in Exam mode)
        with st.expander("See detailed review of all questions"):
            for i, a in enumerate(st.session_state.answers_log, 1):
                st.markdown(f"**Q{i}:** {a['question']}")
                st.write(f"Your answer: {a['your_answer']}")
                st.write(f"Correct answer: {a['correct']}")
                if a["explanation"]:
                    st.write(f"Explanation: {a['explanation']}")
                st.write("---")

    if st.button("Restart with same material"):
        st.session_state.quiz_started = False
        st.session_state.current_question_data = None
        st.session_state.feedback = None
        st.session_state.score = 0
        st.session_state.total_answered = 0
        st.session_state.history = []
        st.session_state.answers_log = []
        st.session_state.finished = False
        st.rerun()

    if st.button("Load new material"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
