import streamlit as st
import json
import random
import time
import os
from datetime import datetime

# ---------------- CONFIG ----------------
st.set_page_config(page_title="USMLE Practice Engine", layout="wide")

QUESTIONS_FILE = "questions.json"
USER_DIR = "user_data"
os.makedirs(USER_DIR, exist_ok=True)

# ---------------- LOAD QUESTIONS ----------------
@st.cache_data
def load_questions():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

questions = load_questions()

# ---------------- USER DATA ----------------
def user_file(username):
    return os.path.join(USER_DIR, f"{username}.json")

def load_user(username):
    path = user_file(username)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {
        "attempted": [],
        "correct": [],
        "incorrect": [],
        "marked": [],
        "confidence": {},
        "stats": {}
    }

def save_user(username, data):
    with open(user_file(username), "w") as f:
        json.dump(data, f, indent=2)

# ---------------- LOGIN ----------------
if "username" not in st.session_state:
    st.title("🔐 Login")
    username = st.text_input("Enter username")
    if st.button("Login") and username:
        st.session_state.username = username
        st.session_state.progress = load_user(username)
        st.experimental_rerun()
    st.stop()

username = st.session_state.username
progress = st.session_state.progress

# Convert lists to sets for logic
for k in ["attempted", "correct", "incorrect", "marked"]:
    progress[k] = set(progress[k])

# ---------------- SESSION STATE ----------------
if "state" not in st.session_state:
    st.session_state.state = {
        "started": False,
        "start_time": None,
        "current_index": 0,
        "session_questions": [],
        "answers": {},
        "show_explanation": False,
        "session_over": False,
        "mode": "reading",
        "time_limit": None,
    }

state = st.session_state.state

# ---------------- UTILITIES ----------------
def elapsed():
    return int(time.time() - state["start_time"])

def save_stats(qid, correct):
    stats = progress["stats"].setdefault(str(qid), {
        "attempts": 0,
        "correct": 0,
        "incorrect": 0
    })
    stats["attempts"] += 1
    stats["correct"] += int(correct)
    stats["incorrect"] += int(not correct)
    stats["last_seen"] = datetime.now().isoformat()

# ---------------- SIDEBAR ----------------
st.sidebar.title(f"👤 {username}")

if st.sidebar.button("Logout"):
    save_user(username, {
        **progress,
        "attempted": list(progress["attempted"]),
        "correct": list(progress["correct"]),
        "incorrect": list(progress["incorrect"]),
        "marked": list(progress["marked"]),
    })
    st.session_state.clear()
    st.experimental_rerun()

st.sidebar.divider()
st.sidebar.title("🧪 Session Setup")

num_q = st.sidebar.slider("Number of questions", 5, 100, 20)

systems = sorted({q["system"] for q in questions})
selected_systems = st.sidebar.multiselect("Systems", systems)

mode = st.sidebar.radio("Mode", ["reading", "test"])

filters = st.sidebar.multiselect(
    "Filters",
    ["unused", "incorrect", "marked"]
)

start = st.sidebar.button("🚀 Start Session")

# ---------------- START SESSION ----------------
if start and not state["started"]:
    pool = questions

    if selected_systems:
        pool = [q for q in pool if q["system"] in selected_systems]

    def allow(q):
        qid = q["id"]
        flags = []
        if "unused" in filters:
            flags.append(qid not in progress["attempted"])
        if "incorrect" in filters:
            flags.append(qid in progress["incorrect"])
        if "marked" in filters:
            flags.append(qid in progress["marked"])
        return any(flags) if filters else True

    pool = [q for q in pool if allow(q)]

    if len(pool) < num_q:
        st.warning("Not enough questions for these filters.")
        st.stop()

    selected = random.sample(pool, num_q)
    for q in selected:
        random.shuffle(q["options"])

    state.update({
        "started": True,
        "start_time": time.time(),
        "current_index": 0,
        "session_questions": selected,
        "answers": {},
        "show_explanation": False,
        "session_over": False,
        "mode": mode,
        "time_limit": 90 * num_q if mode == "test" else None,
    })

# ---------------- TIMER ----------------
if state["started"] and not state["session_over"]:
    if state["mode"] == "test":
        remaining = state["time_limit"] - elapsed()
        st.sidebar.error(f"⏱ {remaining//60}:{remaining%60:02d}")
        if remaining <= 0:
            state["session_over"] = True
    else:
        st.sidebar.info(f"⏱ {elapsed()//60}:{elapsed()%60:02d}")

# ---------------- SESSION OVER ----------------
if state["session_over"]:
    st.title("📊 Session Summary")

    correct = sum(
        1 for q in state["session_questions"]
        if state["answers"].get(q["id"]) == q["answer"]
    )
    total = len(state["session_questions"])

    st.metric("Score", f"{correct}/{total}", f"{correct/total*100:.1f}%")

    for q in state["session_questions"]:
        st.markdown(f"**Q:** {q['question']}")
        st.markdown(f"Your answer: {state['answers'].get(q['id'], '—')}")
        st.markdown(f"Correct answer: {q['answer']}")
        st.info(q["explanation"])

    save_user(username, {
        **progress,
        "attempted": list(progress["attempted"]),
        "correct": list(progress["correct"]),
        "incorrect": list(progress["incorrect"]),
        "marked": list(progress["marked"]),
    })

    if st.button("🔁 New Session"):
        st.session_state.state["started"] = False
        st.experimental_rerun()

    st.stop()

# ---------------- QUESTION VIEW ----------------
if state["started"]:
    q = state["session_questions"][state["current_index"]]
    qid = q["id"]

    st.title(f"Question {state['current_index']+1}/{len(state['session_questions'])}")
    st.markdown(q["question"])

    choice = st.radio("Select answer", q["options"], key=str(qid))

    if st.button("Submit"):
        state["answers"][qid] = choice
        correct = choice == q["answer"]

        progress["attempted"].add(qid)
        (progress["correct"] if correct else progress["incorrect"]).add(qid)

        save_stats(qid, correct)

        state["show_explanation"] = state["mode"] == "reading"

    if state["show_explanation"]:
        st.success("Correct!" if choice == q["answer"] else "Incorrect")
        st.info(q["explanation"])

        conf = st.radio("Confidence", ["low", "medium", "high"], horizontal=True)
        progress["confidence"][str(qid)] = conf

        if st.checkbox("Mark for review"):
            progress["marked"].add(qid)

        if st.button("Next"):
            state["current_index"] += 1
            state["show_explanation"] = False
            if state["current_index"] >= len(state["session_questions"]):
                state["session_over"] = True
            st.experimental_rerun()