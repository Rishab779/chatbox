import json
import os
import threading

import websocket


def init_websocket(username):
    """Initializes and returns a new WebSocket connection."""
    base = os.getenv("CHATBOX_WS_BASE", "ws://127.0.0.1:8000").rstrip("/")
    ws_url = f"{base}/ws/{username}"
    ws = websocket.WebSocket()
    ws.connect(ws_url)
    return ws

def _listener_loop(ws, q):
    """
    Background thread loop that constantly reads from the WebSocket.
    Because this is in a separate thread, it is never interrupted by Streamlit reruns!
    """
    while True:
        try:
            message = ws.recv()
            if message:
                data = json.loads(message)
                q.put(data)
        except websocket.WebSocketConnectionClosedException:
            q.put({"error": "Connection closed by server."})
            break
        except Exception as e:
            q.put({"error": str(e)})
            break

def start_background_listener(ws, q, st):
    """
    Starts the daemon thread to listen to the websocket, preventing race conditions.
    """
    if st.session_state.listener_thread is None or not st.session_state.listener_thread.is_alive():
        t = threading.Thread(target=_listener_loop, args=(ws, q), daemon=True)
        t.start()
        st.session_state.listener_thread = t
