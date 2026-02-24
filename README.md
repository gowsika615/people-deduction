# 🧠 Crowd Vision Analytics

> **High-accuracy, real-time crowd detection and zone-based analytics powered by YOLOv8 and FastAPI.**

Upload an image or video of a crowd and instantly get a per-zone head count, a total people count, and an annotated output image — all rendered inside a clean, browser-based dashboard.

---

## ✨ Features

| Feature                   | Description                                                                                                        |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **YOLOv8 Detection**      | Uses `yolov8m.pt` (medium, high-accuracy) for person detection at `conf=0.5`                                       |
| **Head Boxing**           | Draws bounding boxes only around the top ¼ of each detected person for precise head targeting                      |
| **4-Zone Analytics**      | Divides the frame into North-West, North-East, South-West, and South-East quadrants and counts occupants per zone  |
| **Grid Overlay**          | Renders red crosshair divider lines onto the output image for visual zone reference                                |
| **Image & Video Support** | Accepts `.jpg`, `.jpeg`, `.png` images; `.mp4` and `.avi` videos are recognized (frame-by-frame analysis planned)  |
| **Live Dashboard**        | Browser-based UI built with Bootstrap 5 — shows annotated output, total count, and per-zone breakdown in real time |

---

## 🗂️ Project Structure

```
dashboard/
├── backend/
│   └── main.py          # FastAPI app — YOLO inference, zone logic, REST endpoint
├── static/
│   └── index.html       # Frontend dashboard (Bootstrap 5, vanilla JS)
├── yolov8m.pt           # YOLOv8 Medium model weights (~52 MB, active model)
├── yolov8s.pt           # YOLOv8 Small model weights (~22 MB, alternate/lighter)
└── README.md
```

---

## 🏗️ Architecture

```
Browser (index.html)
    │  POST /predict  (multipart form, image/video file)
    ▼
FastAPI (main.py)
    ├── YOLO inference  →  detect persons (class 0, conf ≥ 0.5)
    ├── Head-box crop   →  top ¼ of each bounding box
    ├── Zone assignment →  compare centroid to frame midpoint
    ├── Grid overlay    →  red crosshair drawn on frame
    └── Response        →  { total, zones, image (base64 JPEG) }
    │
    └── Static mount: GET /dashboard/* → static/index.html
```

---

## ⚙️ Prerequisites

- **Python 3.9+** — [Download](https://www.python.org/downloads/)
- **Git** — [Download](https://git-scm.com/)
- `pip` (bundled with Python)

---

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/people-deduction.git
cd people-deduction
```

### 2. Create & Activate a Virtual Environment

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows**
```bash
python -m venv .venv
.venv\Scripts\activate
```

> You should see `(.venv)` prefixed in your terminal prompt once activated.

### 3. Install Dependencies

```bash
pip install fastapi uvicorn ultralytics opencv-python pillow numpy python-multipart
```

> **Note:** Model weights (`yolov8m.pt`, `yolov8s.pt`) in the project root are used automatically. If missing, Ultralytics will download them on first run.

---

## 🚀 Running the Application

From the project root (with your virtual environment active):

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Then open your browser at:

```
http://localhost:8000/dashboard
```

> **Tip:** Use `--reload` during development for auto-restart on code changes. Remove it in production.

---

## � How to Use

### 1. Start the Server

Ensure your virtual environment is activated, then run:

```bash
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Open the Dashboard

Navigate to **[http://localhost:8000/dashboard](http://localhost:8000/dashboard)** in your browser.

### 3. Upload an Image or Video

Click **"Choose File"** in the *Media Upload* panel and select:
- An image (`.jpg`, `.jpeg`, `.png`) for instant analysis, or
- A video (`.mp4`, `.avi`) for frame-by-frame detection *(video support coming soon)*.

### 4. Run Analytics

Click **"RUN ANALYTICS"**. The button will show *Processing…* while the backend runs inference.

### 5. Read the Results

Once complete, the dashboard automatically updates:

| UI Element               | What it Shows                                                    |
| ------------------------ | ---------------------------------------------------------------- |
| **Annotated Image**      | Output frame with cyan head boxes and red zone-divider grid      |
| **Total Detected Heads** | Total people count across all zones                              |
| **Zone Breakdown**       | Per-zone counts — North-West, North-East, South-West, South-East |

> **Tip:** For denser crowds or lower-quality images, try lowering the confidence threshold in `main.py` (`conf=0.4`) to catch more detections.

---

## �🖥️ API Reference

### `POST /predict`

Accepts a multipart form upload and returns crowd analytics.

**Request**

| Field  | Type         | Description                                               |
| ------ | ------------ | --------------------------------------------------------- |
| `file` | `UploadFile` | Image (`.jpg`, `.jpeg`, `.png`) or Video (`.mp4`, `.avi`) |

**Response — Image**

```json
{
  "type": "image",
  "total": 12,
  "zones": {
    "North-West": 3,
    "North-East": 4,
    "South-West": 2,
    "South-East": 3
  },
  "image": "<base64-encoded JPEG string>"
}
```

**Response — Video** *(initial)*

```json
{
  "type": "video",
  "status": "Video file recognized. Starting frame-by-frame inference."
}
```

**Error**

```json
{ "detail": "Unsupported format" }
```
*(HTTP 400)*

---

## 🔧 Configuration

You can switch to the lighter `yolov8s.pt` model for faster inference on lower-spec hardware by editing `backend/main.py`:

```python
# Default (high accuracy)
model = YOLO('yolov8m.pt')

# Faster / lower resource
model = YOLO('yolov8s.pt')
```

Confidence threshold and target class are set in `run_precision_detection`:

```python
results = model.predict(source=img, conf=0.5, classes=0)
#                                    ↑ threshold   ↑ class 0 = person
```

---

## 📌 Notes & Roadmap

- [x] Image upload and inference
- [x] 4-zone head counting  
- [x] Annotated base64 image response
- [x] Static file serving (dashboard at `/dashboard`)
- [ ] Full frame-by-frame video analysis with streaming results
- [ ] WebSocket support for live camera feeds
- [ ] Historical analytics / time-series logging
- [ ] Docker packaging

---

## 📄 License

This project is for internal / research use. Model weights are subject to the [Ultralytics YOLOv8 License](https://github.com/ultralytics/ultralytics/blob/main/LICENSE).
