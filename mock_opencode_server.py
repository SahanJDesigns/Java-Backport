from flask import Flask, jsonify, request
import time
import uuid
import logging

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/v2/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": "mock-server-1.0"})

@app.route('/v2/session', methods=['POST'])
def create_session():
    session_id = str(uuid.uuid4())
    print(f"[Mock Server] Created session {session_id}")
    return jsonify({"id": session_id})

@app.route('/v2/session/<session_id>', methods=['DELETE', 'POST'])
def session_actions(session_id):
    return jsonify({"status": "ok"})

@app.route('/v2/session/<session_id>', methods=['GET'])
def get_session(session_id):
    return jsonify({"id": session_id, "status": "active"})

@app.route('/v2/permission', methods=['GET'])
def get_permissions():
    return jsonify([])

@app.route('/v2/permission/<req_id>/reply', methods=['POST'])
def reply_permission(req_id):
    return jsonify({"status": "ok"})

@app.route('/v2/session/<session_id>/prompt', methods=['POST'])
def send_prompt(session_id):
    print(f"[Mock Server] Received prompt for session {session_id}")
    time.sleep(2)
    return jsonify({"status": "completed"})

@app.route('/v2/session/<session_id>/messages', methods=['GET'])
def get_messages(session_id):
    mock_response = """
Here is the backport for the commit.

```yaml
backport_result:
  status: success
  patch: |
    --- a/test.java
    +++ b/test.java
    @@ -1,1 +1,1 @@
    - old
    + new
  notes: Mocked successful backport!
```
"""
    return jsonify([
        {
            "role": "assistant",
            "parts": [{"type": "text", "text": mock_response}]
        }
    ])

if __name__ == '__main__':
    print("Starting Mock OpenCode Server on http://localhost:4096")
    app.run(host='127.0.0.1', port=4096, debug=False)
