# 🦺 AI-Based PPE Kit Compliance Monitoring System

A real, full-stack, enterprise-grade AI computer vision web application designed to monitor workplace safety compliance and Personal Protective Equipment (PPE) adherence (Safety Helmets, High-Visibility Vests, Goggles, Gloves, Face Masks, and Safety Boots) in real-time from laptop webcams, uploaded photos, and uploaded video streams.

---

## 🏗️ System Architecture

```
                       +-------------------------------------------------------+
                       |              React + Vite Web Application             |
                       |                  (Tailwind CSS + Lucide)              |
                       +-------------------------------------------------------+
                                    |                           ^
                           HTTP REST / Multipart        HTTP JSON Response / HUD
                                    |                           |
                                    v                           |
                       +-------------------------------------------------------+
                       |             Python Flask Backend & AI Engine          |
                       |                   (Port 5000 / localhost)             |
                       +-------------------------------------------------------+
                                    |                           |
                     +---------------------------+   +---------------------------+
                     |  Ultralytics YOLO Vision  |   |    Database Persistence   |
                     |  • YOLOv8 Neural Network  |   |    • MongoDB / PyMongo    |
                     |  • Person-to-PPE Engine   |   |    • JWT Session Store    |
                     |  • HUD Visual Annotator   |   |    • Compliance Audit Log |
                     +---------------------------+   +---------------------------+
```

### 1. Frontend (`/frontend`)
- **Framework**: React 19 + Vite 6
- **Styling**: Tailwind CSS v4 (Industrial Dark Theme)
- **Visuals**: Recharts (Trends, Zone adherence, PPE breakdown) + Lucide Icons
- **Routing**: React Router v7 with RBAC Protected Routes (`admin`, `reviewer`)
- **Camera Feed**: Native HTML5 `navigator.mediaDevices.getUserMedia()` with throttled inference loop and canvas overlays

### 2. Backend (`/backend`)
- **Server**: Python 3.14 + Flask + Flask-CORS
- **Computer Vision**: Ultralytics YOLOv8 + OpenCV (`cv2`) + NumPy + Pillow
- **Database**: MongoDB (PyMongo) with resilient local collection fallback
- **Authentication**: JWT Token Generation (`pyjwt`) + Secure Password Hashing (`werkzeug.security`)
- **Compliance Rules**: Multi-zone PPE enforcement rules (`helmet`, `vest`, `goggles`, `gloves`, `mask`, `boots`)

---

## 🚀 Quick Start Guide (Windows)

### Prerequisites
1. **Node.js** (v20.x or higher)
2. **Python** (3.10 to 3.14)
3. **Webcam** (built-in laptop webcam or USB webcam)
4. *(Optional)* **MongoDB** (Local `mongod` or MongoDB Atlas URI in `.env`)

---

### Step 1: Start the Python Flask Backend

Open **Terminal 1** (PowerShell):

```powershell
cd "d:\PPE KIT\backend"

# Start the Flask API server
python app.py
```

> **API Server URL**: `http://localhost:5000`  
> On first startup, Ultralytics will automatically load/verify `yolov8n.pt` and initialize default safety zones and admin credentials.

---

### Step 2: Start the React Frontend

Open **Terminal 2** (PowerShell):

```powershell
cd "d:\PPE KIT\frontend"

# Launch Vite development server
npm run dev
```

> **Web Application URL**: `http://localhost:5173`

---

## 🔑 Default Credentials

The system includes pre-configured demo credentials for safety testing:

| Role | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin@ppe.com` | `Admin@123` | Full access (User & Zone Governance, Analytics) |
| **Compliance Reviewer** | `reviewer@ppe.com` | `Reviewer@123` | Live Monitoring, Incident Review, Reports |

*(Quick-fill buttons are provided directly on the Login screen).*

---

## 🛡️ Core Features & Workflows

### 1. Live Camera Surveillance (`/live`)
- **Real-Time Stream**: Browser webcam capture with start/stop lifecycle.
- **Throttling Slider**: Configure processing rate from 400ms to 2000ms to save CPU cycles.
- **HUD Overlays**: High-contrast bounding boxes around workers (Green = Compliant, Red = Violation, Amber = Uncertain).
- **Audio Alarm**: Optional synthesized high-frequency beep alert upon detecting non-compliance.
- **Zone Filtering**: Switch between different facility zones to test dynamic compliance rules.
- **Event Logging**: Click **Log Event** to record forensic snapshots directly into the MongoDB audit ledger.

### 2. Image & Video Compliance Inspector (`/upload`)
- **Drag & Drop**: Upload photos (JPG, PNG) or videos (MP4, WebM) up to 50MB.
- **Frame-by-Frame Video Analysis**: Samples video frames and generates progress metrics, total violation counts, and frame breakdown.
- **Forensic Export**: Save uploaded detection incidents to the safety history.

### 3. Incident Ledger & Supervisor Reviews (`/violations`)
- Search by zone name or missing PPE gear.
- Filter by compliance status (`VIOLATION`, `UNCERTAIN`, `COMPLIANT`) and review state (`PENDING`, `REVIEWED`, `RESOLVED`).
- Modal inspector with high-resolution evidence snapshots and supervisor notes.

### 4. Zone Governance (`/zones`)
- Create and edit safety zones (e.g., Heavy Assembly Bay, Chemical Paint Lab).
- Mandate specific gear combinations per zone (Helmets, Vests, Goggles, Gloves, Masks, Boots).

### 5. Audit Analytics & CSV Reports (`/reports`)
- 7-day compliance trajectory and PPE violation frequency distributions.
- Real-time CSV report generation and download.

---

## 🧪 Automated Testing

To run the backend test suite covering health, auth, YOLO inference, event logging, and CSV exports:

```powershell
cd "d:\PPE KIT\backend"
python test_backend.py
```

To run the frontend production build verification:

```powershell
cd "d:\PPE KIT\frontend"
npm run build
```

---

## 📁 Project Structure

```
d:/PPE KIT/
├── backend/
│   ├── ai_engine/
│   │   ├── compliance.py       # Spatial Person-to-PPE association & compliance engine
│   │   └── ppe_model.py        # Ultralytics YOLO loader & detection pipeline
│   ├── routes/
│   │   ├── auth_routes.py      # JWT authentication routes
│   │   ├── dashboard_routes.py # Summary metrics and trends aggregation
│   │   ├── detection_routes.py # Image/video inference & event endpoints
│   │   ├── health_routes.py    # Service diagnostics
│   │   ├── report_routes.py    # Analytics & CSV export
│   │   ├── user_routes.py      # User management CRUD
│   │   └── zone_routes.py      # Zone rules CRUD
│   ├── app.py                  # Main Flask application entrypoint
│   ├── auth.py                 # JWT token utilities & decorators
│   ├── config.py               # Environment configuration
│   ├── database.py             # MongoDB connection & resilient fallback
│   ├── test_backend.py         # Automated test suite
│   ├── train_model.py          # Custom PPE fine-tuning script
│   ├── requirements.txt        # Python dependencies
│   ├── .env                    # Active backend environment variables
│   └── .env.example
│
└── frontend/
    ├── src/
    │   ├── components/         # Navbar, Sidebar, ProtectedRoute
    │   ├── context/            # AuthContext (JWT session state)
    │   ├── pages/              # Login, Dashboard, Live, Upload, Violations, Reports, Zones, Users, Settings
    │   ├── services/           # Axios API client
    │   ├── App.jsx             # React Router layout
    │   ├── index.css           # Tailwind CSS v4 industrial dark theme
    │   └── main.jsx
    ├── package.json
    ├── vite.config.js
    ├── .env                    # Active frontend environment variables
    └── .env.example
```
