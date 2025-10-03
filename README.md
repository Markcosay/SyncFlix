
# 🎬 SyncFlix

SyncFlix is a **watch party web app** built with **Flask + Socket.IO + WebRTC** that allows two users to:

- 📺 Watch local video files **in perfect sync**  
- 🎥 Video call (FaceTime-style) while watching  
- 🎤 Share audio (mic) in real-time  
- 💬 Send text messages inside the room  
- 🔐 Join via a secure room ID (no accounts needed)  

This project is lightweight, works peer-to-peer for video/audio, and uses Flask-SocketIO for real-time sync.

---

## ✨ Features

- **Room system**  
  - Create a private room with a random secure ID  
  - Share the ID with a friend to join  

- **Video sync**  
  - Play / pause / seek updates instantly sync between both users  
  - Drift correction (keeps timeline in sync)  

- **Video chat + mic**  
  - WebRTC P2P streaming for low latency  
  - Toggle camera & mic on/off anytime  

- **Chat**  
  - Simple text chat alongside the video  
  - Messages appear instantly in the chat box  

- **No login required**  
  - No authentication needed — just share room code  
  - Rooms auto-expire when empty  

---

## 🛠️ Tech Stack

- **Backend:** Flask, Flask-SocketIO (with WebSockets)  
- **Frontend:** Bootstrap 5, Vanilla JS, Socket.IO client, WebRTC API  
- **Sync logic:** Room state stored on server, synced via Socket.IO  
- **Video chat:** WebRTC with STUN/TURN (Google STUN, add TURN for production)  

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+  
- Node not required (uses vanilla JS + Socket.IO CDN)  

### Setup
```bash
# Clone repository
git clone https://github.com/yourusername/SyncFlix.git
cd SyncFlix

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
