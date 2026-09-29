import streamlit as st
import requests
import pandas as pd
import sqlite3
import json


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Study Bot Pro",
    page_icon="📚",
    layout="wide"
)


# ============================================================
# LOAD SECRETS
# ============================================================

try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    OPENROUTER_URL = st.secrets["OPENROUTER_URL"]
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]

    FACULTY_PASSWORD = st.secrets["FACULTY_PASSWORD"]
    STUDENT1_PASSWORD = st.secrets["STUDENT1_PASSWORD"]
    STUDENT2_PASSWORD = st.secrets["STUDENT2_PASSWORD"]

except Exception:
    st.error(
        "Application configuration is incomplete. "
        "Please configure the required Streamlit secrets."
    )
    st.stop()


# ============================================================
# DATABASE
# ============================================================

conn = sqlite3.connect(
    "studybot.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student TEXT,
    topic TEXT,
    score INTEGER,
    total INTEGER
)
""")

conn.commit()


# ============================================================
# USERS
# ============================================================

users = {
    "faculty": {
        "password": FACULTY_PASSWORD,
        "role": "faculty"
    },

    "student1": {
        "password": STUDENT1_PASSWORD,
        "role": "student"
    },

    "student2": {
        "password": STUDENT2_PASSWORD,
        "role": "student"
    }
}


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "logged_in": False,
    "username": "",
    "role": "",
    "quiz": [],
    "answers": [],
    "topic": "",
    "generated": False,
    "score_saved": False,
    "quiz_submitted": False,
    "explanation": "",
    "videos": []
}

for key, value in defaults.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# AI FUNCTION
# ============================================================

def call_ai(prompt):

    try:

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "meta-llama/llama-3.1-8b-instruct",

            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            "temperature": 0.7
        }

        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:

            try:
                error_data = response.json()

                if "error" in error_data:

                    if isinstance(error_data["error"], dict):
                        return (
                            "API Error: "
                            + error_data["error"].get(
                                "message",
                                "Unknown API error"
                            )
                        )

                    return f"API Error: {error_data['error']}"

            except Exception:
                pass

            return (
                f"API request failed "
                f"(Status code: {response.status_code})"
            )

        data = response.json()

        if "choices" in data and len(data["choices"]) > 0:

            return data["choices"][0]["message"]["content"]

        if "error" in data:

            if isinstance(data["error"], dict):
                return (
                    "API Error: "
                    + data["error"].get(
                        "message",
                        "Unknown API error"
                    )
                )

            return f"API Error: {data['error']}"

        return "Unable to generate AI response."

    except requests.exceptions.Timeout:

        return "The AI service took too long to respond. Please try again."

    except requests.exceptions.RequestException as e:

        return f"Network error: {e}"

    except Exception as e:

        return f"Unexpected error: {e}"


# ============================================================
# AI EXPLANATION
# ============================================================

def get_explanation(topic):

    prompt = f"""
Explain the topic "{topic}" in simple language suitable for a student.

Use the following structure:

1. Introduction
2. Key Concepts
3. Real-Life Applications
4. Simple Examples
5. Short Summary

Use clear bullet points and avoid unnecessary complexity.
"""

    return call_ai(prompt)


# ============================================================
# AI QUIZ GENERATION
# ============================================================

def get_quiz(topic):

    prompt = f"""
Create exactly 5 multiple-choice questions about "{topic}".

Return ONLY valid JSON.

Use exactly this format:

[
  {{
    "q": "Question",
    "options": [
      "Option A",
      "Option B",
      "Option C",
      "Option D"
    ],
    "ans": "Correct option"
  }}
]

Rules:

- Exactly 5 questions
- Exactly 4 options for each question
- Only one correct answer
- The value of "ans" must exactly match one of the options
- Do not include explanations
- Do not include Markdown
- Return only JSON
"""

    response = call_ai(prompt)

    try:

        start = response.find("[")
        end = response.rfind("]") + 1

        if start == -1 or end == 0:
            return []

        quiz_data = json.loads(
            response[start:end]
        )

        if not isinstance(quiz_data, list):
            return []

        valid_questions = []

        for question in quiz_data:

            if not isinstance(question, dict):
                continue

            if "q" not in question:
                continue

            if "options" not in question:
                continue

            if "ans" not in question:
                continue

            if len(question["options"]) != 4:
                continue

            if question["ans"] not in question["options"]:
                continue

            valid_questions.append(question)

        return valid_questions[:5]

    except Exception:

        return []


# ============================================================
# YOUTUBE VIDEOS
# ============================================================

def get_videos(topic):

    url = "https://www.googleapis.com/youtube/v3/search"

    params = {
        "part": "snippet",
        "q": topic + " tutorial",
        "key": YOUTUBE_API_KEY,
        "maxResults": 3,
        "type": "video"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return []

        data = response.json()

        videos = []

        for item in data.get("items", []):

            video_id = item.get(
                "id",
                {}
            ).get("videoId")

            if video_id:

                title = item.get(
                    "snippet",
                    {}
                ).get(
                    "title",
                    "YouTube Video"
                )

                channel = item.get(
                    "snippet",
                    {}
                ).get(
                    "channelTitle",
                    "YouTube"
                )

                videos.append({
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": title,
                    "channel": channel
                })

        return videos

    except Exception:

        return []


# ============================================================
# SAVE SCORE
# ============================================================

def save_score(user, topic, score, total):

    try:

        cursor.execute(
            """
            INSERT INTO scores
            (student, topic, score, total)
            VALUES (?, ?, ?, ?)
            """,
            (
                user,
                topic,
                score,
                total
            )
        )

        conn.commit()

    except Exception as e:

        st.error(
            f"Unable to save score: {e}"
        )


# ============================================================
# LOGOUT FUNCTION
# ============================================================

def logout():

    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.quiz = []
    st.session_state.answers = []
    st.session_state.topic = ""
    st.session_state.generated = False
    st.session_state.score_saved = False
    st.session_state.quiz_submitted = False
    st.session_state.explanation = ""
    st.session_state.videos = []

    st.rerun()


# ============================================================
# LOGIN PAGE
# ============================================================

if not st.session_state.logged_in:

    st.title("📚 AI Study Bot Pro")

    st.markdown(
        "### 🤖 Learn smarter with AI"
    )

    st.write(
        "Get topic explanations, learning videos "
        "and AI-generated quizzes."
    )

    st.markdown("---")

    st.subheader("🔐 Login")

    username = st.text_input(
        "Username"
    )

    password = st.text_input(
        "Password",
        type="password"
    )

    if st.button(
        "Login",
        use_container_width=True
    ):

        if (
            username in users
            and users[username]["password"] == password
        ):

            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = users[username]["role"]

            st.rerun()

        else:

            st.error(
                "❌ Invalid username or password"
            )

    st.stop()


# ============================================================
# FACULTY DASHBOARD
# ============================================================

if st.session_state.role == "faculty":

    st.sidebar.title(
        f"👤 {st.session_state.username}"
    )

    st.sidebar.success(
        "Faculty Account"
    )

    if st.sidebar.button(
        "🚪 Logout",
        use_container_width=True
    ):

        logout()

    st.title(
        "👨‍🏫 Faculty Dashboard"
    )

    st.write(
        "View student quiz performance."
    )

    st.markdown("---")

    try:

        df = pd.read_sql_query(
            "SELECT * FROM scores",
            conn
        )

        if df.empty:

            st.info(
                "No quiz scores have been recorded yet."
            )

        else:

            st.subheader(
                "📊 Student Scores"
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            st.markdown("---")

            st.subheader(
                "📈 Performance Summary"
            )

            total_attempts = len(df)

            average_score = (
                df["score"] / df["total"] * 100
            ).mean()

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "Total Quiz Attempts",
                    total_attempts
                )

            with col2:

                st.metric(
                    "Average Score",
                    f"{average_score:.1f}%"
                )

    except Exception as e:

        st.error(
            f"Unable to load scores: {e}"
        )

    st.stop()


# ============================================================
# STUDENT SIDEBAR
# ============================================================

st.sidebar.title(
    f"👤 {st.session_state.username}"
)

st.sidebar.caption(
    "Student Account"
)

menu = st.sidebar.radio(
    "Navigation",
    [
        "🏠 Home",
        "📖 Explanation",
        "🎥 Videos",
        "📝 Quiz"
    ]
)

st.sidebar.markdown("---")

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True
):

    logout()


# ============================================================
# MAIN HEADER
# ============================================================

st.title(
    "📚 AI Study Bot Pro"
)

st.caption(
    "AI-powered learning assistant for students"
)


# ============================================================
# TOPIC INPUT
# ============================================================

topic_input = st.text_input(
    "Enter a topic you want to learn",
    value=st.session_state.topic,
    placeholder="Example: Internet of Things"
)


# ============================================================
# GENERATE CONTENT
# ============================================================

if st.button(
    "✨ Generate Content",
    use_container_width=True
):

    if topic_input.strip() == "":

        st.warning(
            "Please enter a topic first."
        )

    else:

        with st.spinner(
            "Generating your learning content..."
        ):

            topic = topic_input.strip()

            quiz = get_quiz(topic)

            explanation = get_explanation(topic)

            videos = get_videos(topic)

        st.session_state.topic = topic

        st.session_state.quiz = quiz

        st.session_state.answers = (
            [None] * len(quiz)
        )

        st.session_state.explanation = explanation

        st.session_state.videos = videos

        st.session_state.generated = True

        st.session_state.score_saved = False

        st.session_state.quiz_submitted = False

        st.success(
            "✅ Content generated successfully!"
        )


# ============================================================
# HOME
# ============================================================

if menu == "🏠 Home":

    st.subheader(
        "Welcome 👋"
    )

    if st.session_state.generated:

        st.success(
            f"Currently learning: "
            f"**{st.session_state.topic}**"
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.info(
                "📖 **Explanation**\n\n"
                "Understand the topic using AI."
            )

        with col2:

            st.info(
                "🎥 **Videos**\n\n"
                "Watch useful YouTube tutorials."
            )

        with col3:

            st.info(
                "📝 **Quiz**\n\n"
                "Test your knowledge."
            )

    else:

        st.write(
            "Enter a topic above and click "
            "**Generate Content** to start learning."
        )


# ============================================================
# EXPLANATION PAGE
# ============================================================

elif menu == "📖 Explanation":

    st.subheader(
        "📖 AI Explanation"
    )

    if st.session_state.generated:

        st.markdown(
            f"### Topic: {st.session_state.topic}"
        )

        st.markdown("---")

        st.write(
            st.session_state.explanation
        )

    else:

        st.info(
            "👉 Please generate a topic first."
        )


# ============================================================
# VIDEOS PAGE
# ============================================================

elif menu == "🎥 Videos":

    st.subheader(
        "🎥 YouTube Learning Videos"
    )

    if st.session_state.generated:

        if st.session_state.videos:

            for video in st.session_state.videos:

                st.markdown(
                    f"### 🎬 {video['title']}"
                )

                st.caption(
                    f"Channel: {video['channel']}"
                )

                st.video(
                    video["url"]
                )

                st.markdown("---")

        else:

            st.warning(
                "No YouTube videos were found."
            )

    else:

        st.info(
            "👉 Please generate a topic first."
        )


# ============================================================
# QUIZ PAGE
# ============================================================

elif menu == "📝 Quiz":

    st.subheader(
        "📝 AI Generated Quiz"
    )

    if not st.session_state.generated:

        st.info(
            "👉 Please generate a topic first."
        )

    elif len(st.session_state.quiz) == 0:

        st.warning(
            "The quiz could not be generated. "
            "Please generate the topic again."
        )

    else:

        st.markdown(
            f"### Topic: {st.session_state.topic}"
        )

        st.markdown(
            f"**Number of Questions: "
            f"{len(st.session_state.quiz)}**"
        )

        st.markdown("---")

        for i, question in enumerate(
            st.session_state.quiz
        ):

            st.markdown(
                f"**Q{i + 1}. {question['q']}**"
            )

            st.radio(
                "Choose your answer:",
                question["options"],
                index=None,
                key=f"quiz_answer_{i}"
            )

            st.divider()

        if st.button(
            "🚀 Submit Quiz",
            use_container_width=True
        ):

            score = 0

            unanswered = 0

            for i, question in enumerate(
                st.session_state.quiz
            ):

                user_answer = st.session_state.get(
                    f"quiz_answer_{i}"
                )

                correct_answer = question["ans"]

                if user_answer is None:

                    unanswered += 1

                elif user_answer == correct_answer:

                    score += 1

            st.session_state.quiz_score = score

            st.session_state.quiz_submitted = True

            if not st.session_state.score_saved:

                save_score(
                    st.session_state.username,
                    st.session_state.topic,
                    score,
                    len(st.session_state.quiz)
                )

                st.session_state.score_saved = True

            st.rerun()


# ============================================================
# QUIZ RESULTS
# ============================================================

if (
    menu == "📝 Quiz"
    and st.session_state.get(
        "quiz_submitted",
        False
    )
):

    st.markdown("---")

    st.subheader(
        "📊 Quiz Results"
    )

    score = st.session_state.quiz_score

    total = len(
        st.session_state.quiz
    )

    percentage = (
        score / total * 100
    )

    st.success(
        f"🎯 FINAL SCORE: {score}/{total}"
    )

    st.progress(
        percentage / 100
    )

    st.write(
        f"**Percentage: {percentage:.1f}%**"
    )

    st.markdown("---")

    for i, question in enumerate(
        st.session_state.quiz
    ):

        user_answer = st.session_state.get(
            f"quiz_answer_{i}"
        )

        correct_answer = question["ans"]

        if user_answer == correct_answer:

            st.success(
                f"Q{i + 1} ✅ Correct\n\n"
                f"Your Answer: {user_answer}"
            )

        elif user_answer is None:

            st.warning(
                f"Q{i + 1} ⚠️ Not Answered\n\n"
                f"Correct Answer: {correct_answer}"
            )

        else:

            st.error(
                f"Q{i + 1} ❌ Wrong\n\n"
                f"Your Answer: {user_answer}\n\n"
                f"Correct Answer: {correct_answer}"
            )

    st.markdown("---")

    if st.button(
        "🔄 Try Another Topic",
        use_container_width=True
    ):

        st.session_state.quiz = []

        st.session_state.answers = []

        st.session_state.topic = ""

        st.session_state.generated = False

        st.session_state.score_saved = False

        st.session_state.quiz_submitted = False

        st.session_state.explanation = ""

        st.session_state.videos = []

        st.rerun()