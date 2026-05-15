import streamlit as st
import queue

def init_session():
    if "username" not in st.session_state:
        st.session_state.username = None
    if "profile_pic_url" not in st.session_state:
        st.session_state.profile_pic_url = ""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "ws" not in st.session_state:
        st.session_state.ws = None
    if "message_queue" not in st.session_state:
        st.session_state.message_queue = queue.Queue()
    if "listener_thread" not in st.session_state:
        st.session_state.listener_thread = None
    if "pdf_summaries" not in st.session_state:
        st.session_state.pdf_summaries = {}

def clear_session():
    if st.session_state.ws:
        try:
            st.session_state.ws.close()
        except Exception:
            pass
        st.session_state.ws = None
    st.session_state.username = None
    st.session_state.profile_pic_url = ""
    st.session_state.messages = []
    st.session_state.message_queue = queue.Queue()
    st.session_state.listener_thread = None
    st.session_state.pdf_summaries = {}
