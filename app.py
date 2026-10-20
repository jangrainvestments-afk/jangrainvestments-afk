
import io
import requests
import streamlit as st
from pypdf import PdfReader

# ---------------- APP CONFIG ----------------
st.set_page_config(
    page_title="StudyNova",
    page_icon="📚",
    layout="wide",
)

MODEL = "@cf/meta/llama-3.1-8b-instruct"
BASE_URL = "https://api.cloudflare.com/client/v4/accounts"


# ---------------- CLOUDFLARE AI ----------------
def get_cloudflare_settings():
    try:
        account_id = str(
            st.secrets["CLOUDFLARE_ACCOUNT_ID"]
        ).strip()
        token = str(
            st.secrets["CLOUDFLARE_API_TOKEN"]
        ).strip()
    except Exception:
        raise RuntimeError(
            "Cloudflare settings are missing. "
            "Check .streamlit/secrets.toml."
        )

    if (
        not account_id
        or not token
        or account_id.startswith("YOUR_")
        or token.startswith("YOUR_")
    ):
        raise RuntimeError(
            "Add your real Cloudflare Account ID and API token "
            "to .streamlit/secrets.toml."
        )

    return account_id, token


def ask_ai(instructions, prompt):
    account_id, token = get_cloudflare_settings()

    url = (
        f"{BASE_URL}/{account_id}/ai/run/{MODEL}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": (
            f"{instructions}\n\n"
            f"User request:\n{prompt}\n\n"
            "Give a clear, accurate, student-friendly answer."
        )
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.Timeout:
        raise RuntimeError(
            "The AI request timed out. Please try again."
        )
    except requests.RequestException:
        raise RuntimeError(
            "Could not connect to Cloudflare. Check your internet."
        )

    if response.status_code == 401:
        raise RuntimeError(
            "Cloudflare rejected the API token. "
            "Check your token and its Workers AI permissions."
        )

    if response.status_code == 429:
        raise RuntimeError(
            "AI request limit reached. Please wait and try again."
        )

    if not response.ok:
        try:
            details = response.json().get("errors", [])
            message = "; ".join(
                str(item.get("message", "API request failed"))
                for item in details
            )
        except Exception:
            message = "API request failed"

        raise RuntimeError(
            f"Cloudflare returned HTTP {response.status_code}: "
            f"{message[:500]}"
        )

    try:
        data = response.json()
        result = data.get("result", {})
        answer = result.get("response", "")

        if not data.get("success", True):
            raise RuntimeError("Cloudflare could not process the request.")

        if not answer:
            raise RuntimeError(
                "The AI returned an empty response. Try again."
            )

        return answer

    except (ValueError, AttributeError):
        raise RuntimeError(
            "Unexpected response from Cloudflare."
        )


# ---------------- PDF READER ----------------
def extract_pdf_text(uploaded_file):
    try:
        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
        pages = []

        for page in reader.pages:
            pages.append(page.extract_text() or "")

        text = "\n".join(pages).strip()

        if not text:
            raise ValueError(
                "No readable text found. This may be a scanned PDF."
            )

        return text[:30000]

    except Exception as exc:
        raise ValueError(f"Could not read this PDF: {exc}")


# ---------------- APP HEADER ----------------
st.title("📚 StudyNova")
st.caption(
    "Your AI study partner — understand more, study smarter."
)

with st.sidebar:
    st.header("⚙️ StudyNova")
    st.write("AI provider: Cloudflare Workers AI")
    st.write("Model:", MODEL)
    st.info(
        "StudyNova uses a hosted AI service. "
        "Requests need internet access and are subject "
        "to your account's usage limits."
    )

    if st.button("Clear saved notes"):
        st.session_state.notes = ""
        st.session_state.pdf_text = ""
        st.session_state.chat_history = []
        st.rerun()


# ---------------- SESSION STATE ----------------
if "notes" not in st.session_state:
    st.session_state.notes = ""

if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ---------------- INPUT AREA ----------------
st.subheader("📝 Your study material")

st.session_state.notes = st.text_area(
    "Paste your notes or chapter text here",
    value=st.session_state.notes,
    height=180,
    placeholder=(
        "Example: Photosynthesis is the process "
        "by which green plants make their food..."
    ),
)

uploaded_pdf = st.file_uploader(
    "Or upload a text-based PDF",
    type=["pdf"],
)

if uploaded_pdf is not None:
    if st.button("📄 Read PDF"):
        try:
            st.session_state.pdf_text = extract_pdf_text(
                uploaded_pdf
            )
            st.success("PDF text extracted successfully!")
        except ValueError as exc:
            st.error(str(exc))

if st.session_state.pdf_text:
    with st.expander("Preview extracted PDF text"):
        st.text(st.session_state.pdf_text[:5000])

material = (
    st.session_state.pdf_text
    or st.session_state.notes
).strip()

st.divider()


# ---------------- STUDY TOOLS ----------------
st.subheader("🎯 Study tools")

col1, col2, col3 = st.columns(3)

with col1:
    summarize = st.button(
        "📖 Summarize",
        use_container_width=True,
    )

with col2:
    explain = st.button(
        "💡 Explain simply",
        use_container_width=True,
    )

with col3:
    quiz = st.button(
        "🧠 Generate quiz",
        use_container_width=True,
    )


def run_study_task(title, instructions, prompt):
    if not material:
        st.warning("Please paste notes or read a PDF first.")
        return

    with st.spinner(f"{title} in progress..."):
        try:
            answer = ask_ai(instructions, prompt)
            st.session_state.last_result = answer
            st.session_state.last_title = title
        except RuntimeError as exc:
            st.error(f"AI request failed: {exc}")


if summarize:
    run_study_task(
        "Summary",
        "You are a helpful study tutor. Summarize the material "
        "into concise notes with headings, key facts, and "
        "important terms. Do not invent facts.",
        f"Summarize these study notes:\n{material[:12000]}",
    )

if explain:
    run_study_task(
        "Simple explanation",
        "You are a patient tutor. Explain difficult ideas "
        "in simple language and use an example when useful. "
        "Stay faithful to the source material.",
        f"Explain these notes simply:\n{material[:12000]}",
    )

if quiz:
    run_study_task(
        "Practice quiz",
        "You are a teacher creating a practice quiz. Write "
        "5 questions based on the supplied material. Mix "
        "multiple-choice and short-answer questions. Put "
        "the answer key after the questions.",
        f"Create a practice quiz from:\n{material[:12000]}",
    )

if "last_result" in st.session_state:
    st.subheader(st.session_state.last_title)
    st.markdown(st.session_state.last_result)
    st.download_button(
        "⬇️ Download result",
        data=st.session_state.last_result,
        file_name="studynova_result.txt",
        mime="text/plain",
    )


# ---------------- ASK AI ----------------
st.divider()
st.subheader("💬 Ask your study tutor")

question = st.text_input(
    "What would you like to understand?",
    placeholder="e.g. Explain photosynthesis step by step",
)

if st.button("Ask AI", use_container_width=True):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        context = (
            f"Use these notes as context:\n{material[:10000]}\n\n"
            if material
            else ""
        )

        with st.spinner("Thinking..."):
            try:
                answer = ask_ai(
                    "You are StudyNova, a friendly and accurate "
                    "study tutor. Explain concepts clearly, "
                    "show steps for academic problems, and "
                    "say when you are unsure.",
                    context + question.strip(),
                )

                st.session_state.chat_history.append(
                    (question.strip(), answer)
                )

            except RuntimeError as exc:
                st.error(f"AI request failed: {exc}")

for user_question, ai_answer in reversed(
    st.session_state.chat_history
):
    with st.chat_message("user"):
        st.write(user_question)

    with st.chat_message("assistant"):
        st.markdown(ai_answer)


# ---------------- FOOTER ----------------
st.divider()
st.caption(
    "StudyNova • Built for learning. Always verify important "
    "facts with your textbook or teacher."
)
