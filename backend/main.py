import cv2
import io
import base64
import csv
import time
import math
import numpy as np
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from PIL import Image
from ultralytics import YOLO

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Crowd Vision Analytics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = YOLO("yolov8m.pt")

# ── Zone configuration ────────────────────────────────────────────────────────

@dataclass
class ZoneConfig:
    # Boundary percentages
    north_h: float = 0.25       # top N% of frame height
    south_h: float = 0.25       # bottom N% of frame height
    east_w: float  = 0.25       # rightmost N% of frame width
    west_w: float  = 0.25       # leftmost N% of frame width
    # Zone toggles
    north_enabled:  bool = True
    south_enabled:  bool = True
    east_enabled:   bool = True
    west_enabled:   bool = True
    center_enabled: bool = True
    # Colors BGR for OpenCV annotation (also sent to frontend)
    colors: dict = field(default_factory=lambda: {
        "North":  (235, 100,  10),
        "South":  (10,  220, 220),
        "East":   (30,  200,  30),
        "West":   (10,   30, 220),
        "Center": (180, 180, 180),
    })
    # Per-zone thresholds
    max_density:    float = 0.0002   # persons / px²
    max_dwell_sec:  float = 60.0     # loitering threshold
    max_velocity:   float = 30.0     # px/s  running threshold
    surge_window:   float = 10.0     # seconds
    surge_delta:    int   = 5        # count jump to trigger surge


ZONE_CONFIG = ZoneConfig()


def assign_zone(cx: int, cy: int, w: int, h: int, cfg: ZoneConfig) -> str:
    """Return zone name for a given centroid."""
    north_boundary = int(h * cfg.north_h)
    south_boundary = int(h * (1 - cfg.south_h))
    west_boundary  = int(w * cfg.west_w)
    east_boundary  = int(w * (1 - cfg.east_w))

    if cy < north_boundary and cfg.north_enabled:
        return "North"
    if cy > south_boundary and cfg.south_enabled:
        return "South"
    if cx < west_boundary and cfg.west_enabled:
        return "West"
    if cx > east_boundary and cfg.east_enabled:
        return "East"
    if cfg.center_enabled:
        return "Center"
    return "Unknown"


# ── Session state ─────────────────────────────────────────────────────────────

@dataclass
class PersonState:
    track_id:   int
    zone:       str
    entry_time: float        # unix timestamp
    last_seen:  float
    positions:  list = field(default_factory=list)   # [(ts, x, y)]
    velocity:   float = 0.0                          # px / s


class SessionState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.persons: dict[int, PersonState] = {}
        self.zone_events: list[dict] = []          # IN/OUT/transition records
        self.anomalies:   list[dict] = []
        self.zone_counts: dict[str, int]  = defaultdict(int)
        self.zone_peaks:  dict[str, int]  = defaultdict(int)
        # surge detection: store (timestamp, count) per zone
        self.zone_history: dict[str, list] = defaultdict(list)
        self.start_time = time.time()
        self.frame_count = 0

    def log_event(self, kind: str, person_id, zone: str, from_zone: str = None,
                  extra: dict = None):
        ev = {
            "kind":      kind,
            "person_id": person_id,
            "zone":      zone,
            "from_zone": from_zone,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "elapsed":   round(time.time() - self.start_time, 1),
        }
        if extra:
            ev.update(extra)
        self.zone_events.append(ev)
        return ev

    def log_anomaly(self, atype: str, zone: str, person_id=None, detail: str = ""):
        ev = {
            "type":      atype,
            "zone":      zone,
            "person_id": person_id,
            "detail":    detail,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "elapsed":   round(time.time() - self.start_time, 1),
        }
        self.anomalies.append(ev)
        return ev

    def to_stats(self) -> dict:
        zones_data = {}
        for z in ["North", "South", "East", "West", "Center"]:
            zones_data[z] = {
                "current": self.zone_counts.get(z, 0),
                "peak":    self.zone_peaks.get(z, 0),
            }
        return {
            "zones":      zones_data,
            "total":      sum(self.zone_counts.values()),
            "anomalies":  self.anomalies[-50:],    # last 50
            "transitions": [e for e in self.zone_events
                            if e["kind"] == "transition"][-30:],
            "frame_count": self.frame_count,
            "elapsed":    round(time.time() - self.start_time, 1),
        }


SESSION = SessionState()


# ── Core detection + zone logic ───────────────────────────────────────────────

ZONE_COLORS_BGR = {
    "North":  (235, 100,  10),
    "South":  (10,  220, 220),
    "East":   (30,  200,  30),
    "West":   (10,   30, 220),
    "Center": (180, 180, 180),
}

def compute_velocity(positions: list) -> float:
    """Average px/s over the last few positions."""
    if len(positions) < 2:
        return 0.0
    recent = positions[-5:]
    total_dist = 0.0
    total_time = 0.0
    for i in range(1, len(recent)):
        t0, x0, y0 = recent[i - 1]
        t1, x1, y1 = recent[i]
        dt = t1 - t0
        if dt > 0:
            total_dist += math.hypot(x1 - x0, y1 - y0)
            total_time += dt
    return round(total_dist / total_time, 2) if total_time > 0 else 0.0


def draw_zone_overlays(img: np.ndarray, cfg: ZoneConfig) -> np.ndarray:
    """Draw transparent colored zone rectangles and labels onto img."""
    h, w = img.shape[:2]
    overlay = img.copy()
    north_b = int(h * cfg.north_h)
    south_b = int(h * (1 - cfg.south_h))
    west_b  = int(w * cfg.west_w)
    east_b  = int(w * (1 - cfg.east_w))

    zones_rects = []
    if cfg.north_enabled:
        zones_rects.append(("North",  (0, 0,       w,       north_b)))
    if cfg.south_enabled:
        zones_rects.append(("South",  (0, south_b, w,       h)))
    if cfg.west_enabled:
        zones_rects.append(("West",   (0, north_b, west_b,  south_b)))
    if cfg.east_enabled:
        zones_rects.append(("East",   (east_b, north_b, w,  south_b)))
    if cfg.center_enabled:
        zones_rects.append(("Center", (west_b, north_b, east_b, south_b)))

    for name, (x1, y1, x2, y2) in zones_rects:
        color = ZONE_COLORS_BGR[name]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)

    cv2.addWeighted(overlay, 0.18, img, 0.82, 0, img)

    # Draw zone borders and labels
    for name, (x1, y1, x2, y2) in zones_rects:
        color = ZONE_COLORS_BGR[name]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{name}: {SESSION.zone_counts.get(name, 0)}"
        lx = x1 + 6
        ly = y1 + 22
        cv2.putText(img, label, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
        cv2.putText(img, label, (lx, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 1)
    return img


def process_frame(img_bgr: np.ndarray, cfg: ZoneConfig,
                  use_tracking: bool = False) -> dict:
    """Run YOLO detection / tracking on a single BGR frame and update session state."""
    h, w = img_bgr.shape[:2]
    now = time.time()

    # Run inference
    if use_tracking:
     results = model.track(
        img_bgr,
        persist=True,
        imgsz=1280,          # 🔥 higher resolution for dense crowds
        conf=0.20,           # 🔥 lower confidence = more people detected
        iou=0.75,            # 🔥 allow overlapping people
        agnostic_nms=True,   # 🔥 prevent NMS from killing close heads
        classes=0,
        verbose=False
    )
    else:
      results = model.predict(
        img_bgr,
        imgsz=1280,          # 🔥 higher resolution
        conf=0.20,           # 🔥 key change
        iou=0.75,
        agnostic_nms=True,
        classes=0,
        verbose=False
    )

    current_ids_in_frame = set()
    new_zone_counts: dict[str, int] = defaultdict(int)

    for result in results:
        boxes = result.boxes
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Head box: top ~20% of bounding box (robust head approximation)
            box_h = y2 - y1
            head_h = int(box_h * 0.20)
            # Safety clamp to avoid zero / overflow
            head_h = max(6, min(head_h, box_h))

            head_y2 = y1 + head_h

            # Head centroid (used for zone assignment)
            cx = (x1 + x2) // 2
            cy = y1 + head_h // 2

            zone = assign_zone(cx, cy, w, h, cfg)
            new_zone_counts[zone] += 1

            # Track ID handling
            if use_tracking and boxes.id is not None:
                track_id = int(boxes.id[i])
            else:
                track_id = i   # image mode: no stable ID

            current_ids_in_frame.add(track_id)

            if track_id not in SESSION.persons:
                p = PersonState(
                    track_id=track_id, zone=zone,
                    entry_time=now, last_seen=now,
                    positions=[(now, cx, cy)],
                )
                SESSION.persons[track_id] = p
                SESSION.log_event("in", track_id, zone)
            else:
                p = SESSION.persons[track_id]
                p.positions.append((now, cx, cy))
                p.velocity = compute_velocity(p.positions)
                p.last_seen = now

                if p.zone != zone:
                    old_zone = p.zone
                    SESSION.log_event("transition", track_id, zone, from_zone=old_zone)
                    _check_cross_zone_anomaly(track_id, old_zone, zone, now)
                    p.zone = zone

            p = SESSION.persons[track_id]

            # Anomaly checks
            _check_person_anomaly(track_id, p, zone, cfg)

            # Draw head box
            color = ZONE_COLORS_BGR.get(zone, (255, 255, 255))
            cv2.rectangle(img_bgr, (x1, y1), (x2, head_y2), color, 2)
            id_label = f"#{track_id}"
            cv2.putText(img_bgr, id_label, (x1, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # Log OUT for disappeared persons (tracking mode only)
    if use_tracking:
        for tid in list(SESSION.persons.keys()):
            if tid not in current_ids_in_frame:
                p = SESSION.persons[tid]
                dwell = round(now - p.entry_time, 1)
                SESSION.log_event("out", tid, p.zone,
                                  extra={"dwell_sec": dwell})
                del SESSION.persons[tid]

    # Update counts + peaks
    for z in ["North", "South", "East", "West", "Center"]:
        SESSION.zone_counts[z] = new_zone_counts.get(z, 0)
        if SESSION.zone_counts[z] > SESSION.zone_peaks.get(z, 0):
            SESSION.zone_peaks[z] = SESSION.zone_counts[z]

    # Surge detection
    _check_surge(new_zone_counts, now, cfg)

    # Draw overlays
    draw_zone_overlays(img_bgr, cfg)
    SESSION.frame_count += 1

    return {
        "zones": dict(SESSION.zone_counts),
        "peaks": dict(SESSION.zone_peaks),
        "total": sum(new_zone_counts.values()),
        "anomalies": SESSION.anomalies[-10:],
        "transitions": [e for e in SESSION.zone_events
                        if e["kind"] == "transition"][-10:],
    }


def _check_person_anomaly(track_id: int, p: PersonState,
                           zone: str, cfg: ZoneConfig):
    now = time.time()
    # Running
    if p.velocity > cfg.max_velocity:
        if not _recent_anomaly(f"running_{track_id}", 10):
            SESSION.log_anomaly("Running", zone, track_id,
                                f"Velocity {p.velocity:.1f} px/s")
    # Loitering
    dwell = now - p.entry_time
    if dwell > cfg.max_dwell_sec:
        if not _recent_anomaly(f"loiter_{track_id}", 30):
            SESSION.log_anomaly("Loitering", zone, track_id,
                                f"Dwell {dwell:.0f}s in {zone}")
    # Stationary
    if len(p.positions) > 10 and p.velocity < 1.0:
        if dwell > 60 and not _recent_anomaly(f"static_{track_id}", 60):
            SESSION.log_anomaly("Stationary", zone, track_id,
                                f"No movement for {dwell:.0f}s in {zone}")


def _check_cross_zone_anomaly(track_id: int, from_zone: str,
                               to_zone: str, now: float):
    # Rapid zone switching
    p = SESSION.persons.get(track_id)
    if p is None:
        return
    transitions = [e for e in SESSION.zone_events
                   if e["kind"] == "transition"
                   and e["person_id"] == track_id]
    recent = [t for t in transitions if now - t["elapsed"] - SESSION.start_time < 5]
    if len(recent) >= 3:
        SESSION.log_anomaly("Rapid Zone Switch", to_zone, track_id,
                            f"Switched zones {len(recent)+1} times in 5s")


def _check_surge(new_counts: dict, now: float, cfg: ZoneConfig):
    for zone, cnt in new_counts.items():
        hist = SESSION.zone_history[zone]
        hist.append((now, cnt))
        # Keep last 30 s
        SESSION.zone_history[zone] = [(t, c) for t, c in hist
                                      if now - t <= 30]
        window = [(t, c) for t, c in SESSION.zone_history[zone]
                  if now - t <= cfg.surge_window]
        if len(window) >= 2:
            oldest_cnt = window[0][1]
            if cnt - oldest_cnt >= cfg.surge_delta:
                if not _recent_anomaly(f"surge_{zone}", 15):
                    SESSION.log_anomaly(
                        "Crowd Surge", zone,
                        detail=f"{zone} jumped {oldest_cnt}→{cnt} in {cfg.surge_window:.0f}s")
        # Abandonment: zone was ≥3 and is now 0
        if len(hist) >= 2 and hist[-2][1] >= 3 and cnt == 0:
            SESSION.log_anomaly("Zone Abandoned", zone,
                                detail=f"{zone} emptied suddenly")


_anomaly_last_seen: dict[str, float] = {}


def _recent_anomaly(key: str, cooldown: float) -> bool:
    now = time.time()
    if now - _anomaly_last_seen.get(key, 0) < cooldown:
        return True
    _anomaly_last_seen[key] = now
    return False


def frame_to_b64(img_bgr: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return base64.b64encode(buf).decode()


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.post("/predict")
async def predict(
    file: UploadFile = File(...),
    north_h: float = Query(0.25),
    south_h: float = Query(0.25),
    east_w:  float = Query(0.25),
    west_w:  float = Query(0.25),
    center:  bool  = Query(True),
):
    SESSION.reset()
    cfg = ZoneConfig(
        north_h=north_h, south_h=south_h,
        east_w=east_w,   west_w=west_w,
        center_enabled=center,
    )
    ZONE_CONFIG.__dict__.update(cfg.__dict__)

    ext = file.filename.split(".")[-1].lower()
    content = await file.read()

    if ext in ("jpg", "jpeg", "png", "webp", "bmp"):
        pil = Image.open(io.BytesIO(content)).convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        stats = process_frame(img, cfg, use_tracking=False)
        return {
            "type":   "image",
            "image":  frame_to_b64(img),
            **stats,
        }

    if ext in ("mp4", "avi", "mov", "mkv"):
        # Return summary endpoint redirect — actual streaming via /predict/video
        return {"type": "video",
                "status": "Use POST /predict/video for streaming video analysis"}

    raise HTTPException(status_code=400, detail="Unsupported format")


@app.post("/predict/video")
async def predict_video(
    file: UploadFile = File(...),
    north_h: float = Query(0.25),
    south_h: float = Query(0.25),
    east_w:  float = Query(0.25),
    west_w:  float = Query(0.25),
    center:  bool  = Query(True),
    sample:  int   = Query(3, description="Process every Nth frame"),
):
    SESSION.reset()
    cfg = ZoneConfig(
        north_h=north_h, south_h=south_h,
        east_w=east_w, west_w=west_w,
        center_enabled=center,
    )

    content = await file.read()
    tmp_path = f"/tmp/crowd_upload_{int(time.time())}.mp4"
    with open(tmp_path, "wb") as f:
        f.write(content)

    import json as _json
    import os

    async def stream_frames():
        cap = cv2.VideoCapture(tmp_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_idx = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % sample == 0:
                    stats = process_frame(frame, cfg, use_tracking=True)
                    payload = {
                        "frame":  frame_idx,
                        "time":   round(frame_idx / fps, 2),
                        "image":  frame_to_b64(frame),
                        **stats,
                    }
                    yield _json.dumps(payload) + "\n"
                frame_idx += 1
        finally:
            cap.release()
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        # Final session stats
        yield _json.dumps({"done": True, **SESSION.to_stats()}) + "\n"

    return StreamingResponse(stream_frames(),
                             media_type="application/x-ndjson")


@app.get("/session/stats")
def session_stats():
    return JSONResponse(SESSION.to_stats())


@app.get("/session/report")
def session_report():
    def generate():
        import io as _io
        buf = _io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "kind", "person_id", "zone", "from_zone",
            "timestamp", "elapsed", "dwell_sec"
        ])
        writer.writeheader()
        for ev in SESSION.zone_events:
            writer.writerow({
                "kind":      ev.get("kind", ""),
                "person_id": ev.get("person_id", ""),
                "zone":      ev.get("zone", ""),
                "from_zone": ev.get("from_zone", ""),
                "timestamp": ev.get("timestamp", ""),
                "elapsed":   ev.get("elapsed", ""),
                "dwell_sec": ev.get("dwell_sec", ""),
            })
            buf.seek(0)
            chunk = buf.read()
            buf.seek(0)
            buf.truncate()
            if chunk:
                yield chunk
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=session_report.csv"},
    )


@app.post("/config/zones")
async def update_zone_config(
    north_h: float = Query(0.25),
    south_h: float = Query(0.25),
    east_w:  float = Query(0.25),
    west_w:  float = Query(0.25),
    center:  bool  = Query(True),
    north:   bool  = Query(True),
    south:   bool  = Query(True),
    east:    bool  = Query(True),
    west:    bool  = Query(True),
    max_density:   float = Query(0.0002),
    max_dwell_sec: float = Query(60.0),
    max_velocity:  float = Query(30.0),
):
    ZONE_CONFIG.north_h         = north_h
    ZONE_CONFIG.south_h         = south_h
    ZONE_CONFIG.east_w          = east_w
    ZONE_CONFIG.west_w          = west_w
    ZONE_CONFIG.center_enabled  = center
    ZONE_CONFIG.north_enabled   = north
    ZONE_CONFIG.south_enabled   = south
    ZONE_CONFIG.east_enabled    = east
    ZONE_CONFIG.west_enabled    = west
    ZONE_CONFIG.max_density     = max_density
    ZONE_CONFIG.max_dwell_sec   = max_dwell_sec
    ZONE_CONFIG.max_velocity    = max_velocity
    return {"status": "ok", "config": ZONE_CONFIG.__dict__}


# ── Static dashboard (must come last) ────────────────────────────────────────
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")
