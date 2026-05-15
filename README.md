# Realtime Chat System

A localhost-based realtime chat system built with FastAPI, Streamlit, and WebSockets.
This project allows two users (Rishab and Blesson) to communicate instantly in separate browser windows.

## Architecture

- **Backend (FastAPI)**: Manages active WebSocket connections using an in-memory `ConnectionManager`. It routes messages to all connected clients except the sender to avoid message duplication.
- **Frontend (Streamlit)**: Uses `websocket-client` to connect to the backend. It uses a non-polling, blocking receive loop at the bottom of the `app.py` script. This efficiently waits for incoming messages and uses `st.rerun()` to update the UI instantly without freezing the app or losing user input.

### Message Flow
1. User types a message in Streamlit's `st.chat_input`.
2. The message is instantly appended to the local `session_state` and rendered.
3. The client sends the message to the FastAPI server via WebSockets.
4. The server receives the message and broadcasts it to all other active WebSockets.
5. The receiving client's blocking `recv()` loop catches the message.
6. The receiving client appends the message to its `session_state` and calls `st.rerun()` to refresh the UI instantly.

## Setup Instructions (macOS)

1. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

You need two separate terminal windows.

**Terminal 1 (Backend Server):**
```bash
# Ensure you are in the project root directory
uvicorn server.main:app --reload --port 8000
```

**Terminal 2 (Frontend Client):**
```bash
# Ensure you are in the project root directory
streamlit run client/app.py
```

## How to Test

1. Open a browser window to `http://localhost:8501`.
2. Select "Rishab" and click "Login".
3. Open a **second** browser window (or incognito window) to the same URL.
4. Select "Blesson" and click "Login".
5. Send messages between the two windows. You will see them appear instantly.

## Troubleshooting

- **Connection Refused**: Ensure the FastAPI server is running on port 8000.
- **Port already in use**: If port 8000 or 8501 is busy, you might need to kill the processes using them (`lsof -i :8000` then `kill -9 <PID>`).
- **Duplicate messages**: Ensure you are only running one instance of the Streamlit app per user, and that you didn't manually refresh the page while a websocket was active. The Streamlit code handles disconnects and reruns automatically.
