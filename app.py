import streamlit as st
import json
import time
from io import StringIO
from pypdf import PdfReader
import pandas as pd

# --- Local Imports ---
from crew_logic import analyze_initial_request, refine_requirements_with_answer, finalize_requirements_document
from dashboard_utils import get_dashboard_data

# --- Page Setup ---
st.set_page_config(page_title="AI Requirements Assistant", layout="wide")

# --- Session State Initialization ---
def init_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "Chatbot"
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "current_chat_id" not in st.session_state: st.session_state.current_chat_id = None
    if "stage" not in st.session_state: st.session_state.stage = "initial"
    if "messages" not in st.session_state: st.session_state.messages = []
    if "requirements" not in st.session_state: st.session_state.requirements = []
    if "clarification_questions" not in st.session_state: st.session_state.clarification_questions = []
    if "question_index" not in st.session_state: st.session_state.question_index = 0
    if "scores" not in st.session_state: st.session_state.scores = {}
    if "final_doc" not in st.session_state: st.session_state.final_doc = None

init_session_state()


# --- UI Rendering Functions ---

def show_dashboard_page():
    st.title("Project Dashboard")
    st.info("This dashboard provides an overview of all projects created in your current session.")
    dashboard_data = get_dashboard_data(st.session_state.chat_history)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Projects", dashboard_data["total_projects"])
    col2.metric("Total Requirements", dashboard_data["total_requirements"])
    col3.metric("Avg Reqs / Project", dashboard_data["avg_requirements_per_project"])
    st.markdown("---")

    col1, col2 = st.columns([2, 3])
    with col1:
        st.subheader("Requirements by Priority")
        if not dashboard_data["priority_counts"].empty and dashboard_data["priority_counts"]["Count"].sum() > 0:
            st.bar_chart(dashboard_data["priority_counts"], x="Priority", y="Count", color="#007BFF")
        else:
            st.info("Complete a project to see priority stats.")
    with col2:
        st.subheader("Recent Projects (This Session)")
        if not dashboard_data["recent_projects"]:
            st.info("No projects started yet. Go to the 'Chatbot' page to create one.")
        else:
            for project in dashboard_data["recent_projects"]:
                with st.container(border=True):
                    p_col1, p_col2 = st.columns([4, 1])
                    p_col1.markdown(f"{project['title']}")
                    p_col1.caption(f"{len(project.get('requirements', []))} requirements")
                    if p_col2.button("Open", key=f"open_{project['id']}", use_container_width=True):
                        load_chat(project['id'])
                        st.session_state.page = "Chatbot"
                        st.rerun()

def show_chatbot_page():
    st.title("🤖 AI Requirements Assistant")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.session_state.stage == "initial":
        with st.form("initial_request_form"):
            user_text = st.text_area("Describe your project or feature:", height=150)
            uploaded_file = st.file_uploader("Or, upload a document (PDF, TXT, MD)", type=['txt', 'pdf', 'md'])
            if st.form_submit_button("Start Analysis", type="primary"):
                doc_content = ""
                if uploaded_file:
                    try:
                        if uploaded_file.type == "application/pdf":
                            reader = PdfReader(uploaded_file)
                            doc_content = "".join(p.extract_text() for p in reader.pages)
                        else:
                            doc_content = StringIO(uploaded_file.getvalue().decode("utf-8")).read()
                    except Exception as e:
                        st.error(f"Error reading file: {e}")
                full_request = user_text + "\n\n" + doc_content
                if full_request.strip():
                    handle_initial_request(full_request.strip())
                    st.rerun()
                else:
                    st.warning("Please describe your project or upload a document.")

    elif st.session_state.stage == "prioritization":
        with st.chat_message("assistant"):
            st.info("Assign a priority score (1-10) for each requirement.")
            scores = {req: st.slider(req, 1, 10, 5, key=f"slider_{req}") for req in st.session_state.requirements}
            if st.button("Generate Document", type="primary"):
                st.session_state.scores = scores
                with st.spinner("🤖 Assembling your final document..."):
                    final_doc = finalize_requirements_document(st.session_state.requirements, scores)
                    st.session_state.final_doc = final_doc
                    st.session_state.stage = "final_document"
                    st.session_state.messages.append({"role": "assistant", "content": final_doc})
                    update_current_chat_in_history()
                    st.rerun()

    if st.session_state.stage == "clarification":
        if prompt := st.chat_input("Your answer..."):
            handle_clarification_answer(prompt)
            st.rerun()

    if st.session_state.final_doc:
        st.markdown("---")
        st.subheader("Document Actions")
        col1, col2 = st.columns(2)
        col1.download_button("📥 Download Document", st.session_state.final_doc, "requirements.md", "text/markdown", use_container_width=True)
        if col2.button("🔄 Update Requirements", use_container_width=True):
            st.session_state.stage = "initial"
            st.session_state.messages.append({"role": "assistant", "content": "Of course! Please describe the changes below."})
            update_current_chat_in_history()
            st.rerun()

# --- Logic Handler Functions ---

# FIX: This function is now smarter and handles both new and existing chats correctly.
def handle_initial_request(user_input):
    # If there is no active chat ID, this is a brand new project. Create a new ID.
    if st.session_state.current_chat_id is None:
        st.session_state.current_chat_id = time.time()
        st.session_state.messages = [{"role": "user", "content": "Here is my project idea."}]
    else:
        # This is an existing chat being updated. We preserve the ID and append to messages.
        st.session_state.messages.append({"role": "user", "content": "Here are my updates."})

    with st.spinner("🤖 Analyzing your request..."):
        try:
            # The AI logic for analysis is the same for new projects and updates.
            result = json.loads(analyze_initial_request(user_input))
            st.session_state.requirements = result.get("initial_requirements", [])
            st.session_state.clarification_questions = result.get("clarifying_questions", [])
            st.session_state.question_index = 0
            st.session_state.stage = "clarification"
            if st.session_state.clarification_questions:
                q = st.session_state.clarification_questions[0]
                st.session_state.messages.append({"role": "assistant", "content": f"Thanks for the update! I have a few more questions to clarify.\n\n*1. {q}*"})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "Thanks! Your updates are very clear. Let's move on to prioritization."})
                st.session_state.stage = "prioritization"
        except Exception as e:
            st.error(f"Sorry, an error occurred during analysis. Please try again. Error: {e}")
    
    # Save the changes to the project (either new or existing)
    update_current_chat_in_history()

def handle_clarification_answer(user_answer):
    st.session_state.messages.append({"role": "user", "content": user_answer})
    q_index = st.session_state.question_index
    current_q = st.session_state.clarification_questions[q_index]
    with st.spinner("Thinking..."):
        try:
            result = json.loads(refine_requirements_with_answer(st.session_state.requirements, current_q, user_answer))
            st.session_state.requirements = result.get("updated_requirements", st.session_state.requirements)
            st.session_state.question_index += 1
            if st.session_state.question_index < len(st.session_state.clarification_questions):
                next_q = st.session_state.clarification_questions[st.session_state.question_index]
                st.session_state.messages.append({"role": "assistant", "content": f"Got it. Next:\n\n*{st.session_state.question_index + 1}. {next_q}*"})
            else:
                req_list = "\n".join([f"- {req}" for req in st.session_state.requirements])
                st.session_state.messages.append({"role": "assistant", "content": f"Great, that's everything! Here's the consolidated list:\n\n{req_list}\n\nNow, let's prioritize."})
                st.session_state.stage = "prioritization"
        except Exception as e:
            st.error(f"Sorry, an error occurred while processing your answer. Error: {e}")
    update_current_chat_in_history()

# --- Session History Management Functions ---

def update_current_chat_in_history():
    if st.session_state.current_chat_id:
        # Use the first user message to create a consistent title.
        first_user_message = next((msg['content'] for msg in st.session_state.messages if msg['role'] == 'user'), "Project Idea")
        title = f"{first_user_message[:40]}..."
        chat_data = {
            'id': st.session_state.current_chat_id, 'title': title,
            'messages': st.session_state.messages, 'requirements': st.session_state.requirements,
            'final_doc': st.session_state.final_doc, 'stage': st.session_state.stage,
            'clarification_questions': st.session_state.clarification_questions,
            'question_index': st.session_state.question_index,
            'prioritization_scores': st.session_state.scores
        }
        chat_index = next((i for i, chat in enumerate(st.session_state.chat_history) if chat["id"] == chat_data['id']), -1)
        if chat_index != -1:
            st.session_state.chat_history[chat_index] = chat_data
        else:
            st.session_state.chat_history.insert(0, chat_data)

def start_new_chat():
    # We save the state of the old chat before wiping the slate clean for the new one.
    update_current_chat_in_history()
    st.session_state.stage = "initial"
    st.session_state.messages = []
    st.session_state.requirements = []
    st.session_state.current_chat_id = None
    st.session_state.clarification_questions = []
    st.session_state.question_index = 0
    st.session_state.scores = {}
    st.session_state.final_doc = None
    st.rerun()

def load_chat(chat_id):
    update_current_chat_in_history()
    chat_to_load = next((chat for chat in st.session_state.chat_history if chat["id"] == chat_id), None)
    if chat_to_load:
        for key, value in chat_to_load.items():
            st.session_state[key] = value
    # No rerun here, it's handled by the button click logic.

# --- Main App Controller ---

def main():
    with st.sidebar:
        st.title("Menu")
        st.session_state.page = st.radio("Navigation", ["Chatbot", "Dashboard"], label_visibility="collapsed")
        if st.session_state.page == "Chatbot":
            if st.button("➕ New Conversation", type="primary"):
                start_new_chat()
            st.markdown("### Chat History (This Session)")
            for chat in st.session_state.chat_history:
                if st.button(chat["title"], key=f"load_{chat['id']}"):
                    load_chat(chat['id'])
                    st.rerun()

    if st.session_state.page == "Dashboard":
        show_dashboard_page()
    else:
        show_chatbot_page()

# --- App Entry Point ---
if __name__ == "__main__":
    main()