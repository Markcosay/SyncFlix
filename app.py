import secrets
import threading
import time
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'replace-with-a-real-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory rooms structure:
# rooms[room_id] = {
#   'host_sid': <sid>,
#   'client_sid': <sid> or None,
#   'video_hash': <sha256>,
#   'filename': <filename>,
#   'state': {'time': 0.0, 'paused': True},
#   'last_active': timestamp
# }
rooms = {}
room_locks = {}

ROOM_TTL_SECONDS = 60 * 60  # 1 hour (unused users will get removed if both gone)

def generate_room_id():
    # Longer, unguessable id for production-like security
    return secrets.token_urlsafe(12)

def cleanup_worker():
    while True:
        now = time.time()
        to_delete = []
        for rid, meta in list(rooms.items()):
            if meta.get('host_sid') is None and meta.get('client_sid') is None:
                # If no participants, delete
                to_delete.append(rid)
            else:
                # optional: expire rooms older than TTL since last_active
                if now - meta.get('last_active', now) > ROOM_TTL_SECONDS:
                    to_delete.append(rid)
        for rid in to_delete:
            try:
                del rooms[rid]
                del room_locks[rid]
                print(f"[cleanup] removed room {rid}")
            except KeyError:
                pass
        time.sleep(60)

cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create')
def create_page():
    return render_template('create.html')

@app.route('/join')
def join_page():
    return render_template('join.html')

# Socket events --------------------------------------------------------------
@socketio.on('create_room')
def handle_create_room(data):
    video_hash = data.get('video_hash')
    filename = data.get('filename')
    if not video_hash or not filename:
        emit('error', {'message': 'Missing video metadata'})
        return

    room_id = generate_room_id()
    while room_id in rooms:
        room_id = generate_room_id()

    rooms[room_id] = {
        'host_sid': request.sid,
        'client_sid': None,
        'video_hash': video_hash,
        'filename': filename,
        'state': {'time': 0.0, 'paused': True},
        'last_active': time.time()
    }
    room_locks[room_id] = threading.Lock()
    join_room(room_id)
    print(f"[room] created {room_id} by {request.sid}")
    emit('room_created', {'room_id': room_id, 'filename': filename})

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data.get('room_id')
    video_hash = data.get('video_hash')
    if not room_id:
        emit('error', {'message': 'Missing room id'})
        return

    if room_id not in rooms:
        emit('error', {'message': f'Room {room_id} not found'})
        return

    with room_locks[room_id]:
        if rooms[room_id]['client_sid'] is not None:
            emit('error', {'message': 'Room is full'})
            return
        # Verify video hash
        if video_hash != rooms[room_id]['video_hash']:
            emit('error', {'message': 'Video file mismatch! Make sure you selected the same file as the host.'})
            return

        rooms[room_id]['client_sid'] = request.sid
        rooms[room_id]['last_active'] = time.time()
        join_room(room_id)
        print(f"[room] {request.sid} joined {room_id}")
        # send current state to new peer
        emit('sync_state', rooms[room_id]['state'], room=request.sid)
        # notify host that peer joined
        host_sid = rooms[room_id]['host_sid']
        if host_sid:
            emit('peer_joined', {'message': 'Peer joined'}, room=host_sid)
        # tell both ready to start camera/rtc negotiation
        emit('ready_for_call', room=room_id)

@socketio.on('control')
def handle_control(data):
    room_id = data.get('room_id')
    action = data.get('action')
    time_val = float(data.get('time', rooms.get(room_id, {}).get('state', {}).get('time', 0.0)))

    if not room_id or room_id not in rooms:
        return

    with room_locks[room_id]:
        # update canonical state
        if action == 'play':
            rooms[room_id]['state']['paused'] = False
        elif action == 'pause':
            rooms[room_id]['state']['paused'] = True
        elif action == 'seek':
            rooms[room_id]['state']['time'] = time_val

        # keep latest time always
        rooms[room_id]['state']['time'] = time_val
        rooms[room_id]['last_active'] = time.time()

        # route to other participant only (avoid echo)
        host = rooms[room_id]['host_sid']
        client = rooms[room_id]['client_sid']
        target = client if request.sid == host else host
        if target:
            emit('sync_state', rooms[room_id]['state'], room=target)

@socketio.on('state_update')
def handle_state_update(data):
    """
    Periodic heartbeat from host with latest time/paused to reduce drift.
    Should be emitted from host periodically (e.g., every 2s).
    """
    room_id = data.get('room_id')
    time_val = float(data.get('time', 0.0))
    paused = bool(data.get('paused', True))
    if not room_id or room_id not in rooms:
        return
    with room_locks[room_id]:
        rooms[room_id]['state']['time'] = time_val
        rooms[room_id]['state']['paused'] = paused
        rooms[room_id]['last_active'] = time.time()
        # send only to the other participant
        host = rooms[room_id]['host_sid']
        client = rooms[room_id]['client_sid']
        target = client if request.sid == host else host
        if target:
            emit('sync_state', rooms[room_id]['state'], room=target)

# WebRTC signaling: offer / answer / ice -------------------------------------
def route_to_peer(room_id, payload):
    """Utility: send payload to the other peer (not the sender)."""
    if room_id not in rooms:
        return
    host = rooms[room_id]['host_sid']
    client = rooms[room_id]['client_sid']
    target = client if request.sid == host else host
    if target:
        emit(payload['event'], payload['data'], room=target)

@socketio.on('offer')
def handle_offer(data):
    # data should contain: room_id, offer
    room_id = data.get('room_id')
    if not room_id or room_id not in rooms:
        return
    payload = {'event': 'offer', 'data': {'room_id': room_id, 'offer': data.get('offer')}}
    route_to_peer(room_id, payload)

@socketio.on('answer')
def handle_answer(data):
    room_id = data.get('room_id')
    if not room_id or room_id not in rooms:
        return
    payload = {'event': 'answer', 'data': {'room_id': room_id, 'answer': data.get('answer')}}
    route_to_peer(room_id, payload)

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    room_id = data.get('room_id')
    candidate = data.get('candidate')
    if not room_id or room_id not in rooms:
        return
    payload = {'event': 'ice_candidate', 'data': {'room_id': room_id, 'candidate': candidate}}
    route_to_peer(room_id, payload)

# Chat messages
@socketio.on('chat_message')
def handle_chat_message(data):
    room_id = data.get('room_id')
    msg = data.get('message')
    sender = request.sid
    if not room_id or room_id not in rooms:
        return
    with room_locks[room_id]:
        emit('chat_message', {'sender': sender, 'message': msg}, room=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"[disconnect] {sid}")
    for room_id, meta in list(rooms.items()):
        changed = False
        if meta.get('host_sid') == sid:
            meta['host_sid'] = None
            changed = True
            print(f"[room] host left {room_id}")
        if meta.get('client_sid') == sid:
            meta['client_sid'] = None
            changed = True
            print(f"[room] client left {room_id}")
        if changed:
            meta['last_active'] = time.time()
        # If both are gone, we will cleanup in background thread

if __name__ == '__main__':
    print("Starting SyncFlix server...")
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
