import json
import time
import queue
from flask import Blueprint, Response, request

event_bp = Blueprint("event_bp", __name__)

# Thread-safe queue list for connected SSE clients
_clients = []

def register_client():
    q = queue.Queue(maxsize=50)
    _clients.append(q)
    return q

def unregister_client(q):
    if q in _clients:
        _clients.remove(q)

def broadcast_event(event_type, data):
    """
    Broadcasts an event payload to all active SSE subscribers (Admin & Supervisor dashboards).
    """
    message = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": time.time()
    }, default=str)
    dead_clients = []
    for q in list(_clients):
        try:
            q.put_nowait(message)
        except queue.Full:
            dead_clients.append(q)
        except Exception:
            dead_clients.append(q)
    
    for dead in dead_clients:
        unregister_client(dead)

@event_bp.route("/api/events/stream", methods=["GET"])
def event_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time live alert dispatch.
    Browsers subscribe to this stream for zero-latency alarm triggers and notifications.
    """
    client_queue = register_client()

    def stream():
        # Send initial connected handshake
        yield f"event: ping\ndata: {json.dumps({'status': 'connected'})}\n\n"
        try:
            while True:
                try:
                    # Wait for up to 20 seconds for an event
                    message = client_queue.get(timeout=20.0)
                    yield f"event: message\ndata: {message}\n\n"
                except queue.Empty:
                    # Keep-alive heartbeat comment to prevent proxy timeouts
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            unregister_client(client_queue)
        except Exception:
            unregister_client(client_queue)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )
