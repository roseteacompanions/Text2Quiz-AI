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
You are Text2Quiz AI, an expert educational quiz generator.
Rules you MUST follow:
1. Use ONLY information from the source material. Never invent facts.
2. Create high-quality questions that test important concepts.
3. Avoid repeating the same concept in the same way.
4. Vary difficulty: start easier, then move to intermediate and harder reasoning.
5. Return your response in the exact JSON format requested.
"""

# ====================== HELPER FUNCTIONS ======================
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

def parse_json_from_text(text):
    """Extract JSON from the model response"""
    try:
        # Try to find JSON block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except:
        return None

# ====================== SESSION STATE ======================
if "source_text" not in st.session_state:
    st.session_state.source_text = ""
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "current_q" not in st.session_state:
    st.session_state.current_q = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "total_answered" not in st.session_state:
    st.session_state.total_answered = 0
if "history" not in st.session_state:
    st.session_state.history = []          # list of past questions (to avoid repetition)
if "current_question_data" not in st.session_state:
    st.session_state.current_question_data = None
if "feedback" not in st.session_state:
    st.session_state.feedback = None
if "finished" not in st.session_state:
    st.session_state.finished = False

# ====================== PAGE CONFIG ======================
st.set_page_config(page_title="Text2Quiz AI", page_icon="📝", layout="centered")
st.title("Text2Quiz AI – Interactive Practice")

# ====================== LOAD MATERIAL ======================
if not st.session_state.quiz_started:
    st.subheader("1. Load your study material")
    text_input = st.text_area("Paste text here", height=180)
    uploaded_file = st.file_uploader("Or upload PDF / Word file", type=["pdf", "docx", "txt"])

    if st.button("Load Material", type="primary"):
        source = text_input.strip() if text_input else ""
        if uploaded_file:
            file_text = extract_text_from_file(uploaded_file)
            if file_text.startswith("Error"):
                st.error(file_text)
            else:
                source = (source + "\n\n" + file_text) if source else file_text

        if len(source) < 50:
            st.warning("Please provide more content (at least a few paragraphs).")
        else:
            st.session_state.source_text = source[:25000]
            st.session_state.quiz_started = False
            st.session_state.current_q = 0
            st.session_state.score = 0
            st.session_state.total_answered = 0
            st.session_state.history = []
            st.session_state.current_question_data = None
            st.session_state.feedback = None
            st.session_state.finished = False
            st.success("Material loaded! You can now start the quiz.")
            st.rerun()

# ====================== START QUIZ ======================
if st.session_state.source_text and not st.session_state.quiz_started:
    st.success("Material is ready.")
    if st.button("Start Practice Quiz (one question at a time)", type="primary"):
        st.session_state.quiz_started = True
        st.session_state.finished = False
        st.rerun()

# ====================== GENERATE ONE QUESTION ======================
def generate_next_question():
    history_text = ""
    if st.session_state.history:
        history_text = "Previously asked questions (do NOT repeat these concepts in the same way):\n"
        for h in st.session_state.history[-8:]:
            history_text += f"- {h}\n"

    difficulty = "easy"
    if st.session_state.total_answered >= 4:
        difficulty = "intermediate"
    if st.session_state.total_answered >= 9:
        difficulty = "difficult"

    prompt = f"""
{SYSTEM_PROMPT}

SOURCE MATERIAL:
\"\"\"
{st.session_state.source_text}
\"\"\"

{history_text}

Create ONE new question of difficulty level: {difficulty}.
Choose the most appropriate type from: multiple_choice, true_false, fill_blank, short_answer.

Return ONLY valid JSON in this exact format (no extra text):

{{
  "type": "multiple_choice",
  "question": "the question text",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct": "B",
  "explanation": "short explanation why this is correct",
  "concept": "short name of the concept being tested"
}}

For true_false use options: ["True", "False"] and correct: "True" or "False"
For fill_blank and short_answer: options can be empty list [], correct is the expected answer text.
"""

    raw = call_gemini(prompt)
    data = parse_json_from_text(raw)

    if data is None:
        st.error("Failed to generate a valid question. Trying again...")
        st.write(raw)
        return None
    return data

# ====================== QUIZ INTERFACE ======================
if st.session_state.quiz_started and not st.session_state.finished:

    # Generate first or next question if needed
    if st.session_state.current_question_data is None:
        with st.spinner("Generating next question..."):
            qdata = generate_next_question()
            if qdata:
                st.session_state.current_question_data = qdata
                st.session_state.feedback = None
            else:
                st.stop()

    q = st.session_state.current_question_data

    st.markdown(f"### Question {st.session_state.total_answered + 1}")
    st.write(q["question"])

    user_answer = None

    # Different input types
    if q["type"] == "multiple_choice":
        options = q.get("options", [])
        user_answer = st.radio("Choose your answer:", options, key=f"q_{st.session_state.total_answered}")
    elif q["type"] == "true_false":
        user_answer = st.radio("Choose:", ["True", "False"], key=f"q_{st.session_state.total_answered}")
    elif q["type"] in ["fill_blank", "short_answer"]:
        user_answer = st.text_input("Type your answer:", key=f"q_{st.session_state.total_answered}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Submit Answer", type="primary"):
            if not user_answer:
                st.warning("Please select or type an answer.")
            else:
                # Simple checking
                correct = str(q.get("correct", "")).strip().lower()
                given = str(user_answer).strip().lower()

                # For multiple choice we often get "B) text" → extract letter
                if q["type"] == "multiple_choice" and ")" in given:
                    given = given.split(")")[0].strip().lower()

                is_correct = correct in given or given in correct or given == correct

                st.session_state.total_answered += 1
                if is_correct:
                    st.session_state.score += 1
                    st.session_state.feedback = ("correct", q.get("explanation", "Correct!"))
                else:
                    st.session_state.feedback = ("wrong", f"Incorrect. Correct answer: {q.get('correct')}\n\n{q.get('explanation', '')}")

                # Save to history to reduce repetition
                st.session_state.history.append(q.get("concept", q["question"][:60]))
                st.rerun()

    with col2:
        if st.button("End Quiz & Show Results"):
            st.session_state.finished = True
            st.rerun()

    # Show feedback
    if st.session_state.feedback:
        kind, message = st.session_state.feedback
        if kind == "correct":
            st.success(message)
        else:
            st.error(message)

        if st.button("Next Question →"):
            st.session_state.current_question_data = None
            st.session_state.feedback = None
            st.rerun()

# ====================== FINAL STATISTICS ======================
if st.session_state.finished:
    st.header("Quiz Results")
    total = st.session_state.total_answered
    score = st.session_state.score

    if total == 0:
        st.write("No questions answered.")
    else:
        percent = round(score / total * 100)
        st.metric("Score", f"{score} / {total}  ({percent}%)")

        st.subheader("Where to improve")
        if percent >= 80:
            st.success("Excellent work! You have a strong understanding of the material.")
        elif percent >= 60:
            st.info("Good effort. Review the concepts you missed and try again.")
        else:
            st.warning("You need more practice on the main concepts. Go back to the material and restart the quiz.")

        st.write("Concepts you practiced:")
        for h in st.session_state.history:
            st.write(f"- {h}")

    if st.button("Restart Quiz"):
        st.session_state.quiz_started = False
        st.session_state.current_q = 0
        st.session_state.score = 0
        st.session_state.total_answered = 0
        st.session_state.history = []
        st.session_state.current_question_data = None
        st.session_state.feedback = None
        st.session_state.finished = False
        st.rerun()
