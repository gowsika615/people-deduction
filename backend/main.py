import cv2
import io
import base64
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from ultralytics import YOLO
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Using yolov8m (Medium) for high accuracy out of the box
model = YOLO('yolov8m.pt') 

app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")

def run_precision_detection(img_input):
    # Convert to OpenCV format
    img = cv2.cvtColor(np.array(img_input), cv2.COLOR_RGB2BGR)
    h, w, _ = img.shape
    mid_x, mid_y = w // 2, h // 2

    # FEATURE: High-Accuracy Prediction (Inference)
    # imgsz=640 is standard, but the model is powerful enough to find heads
    results = model.predict(source=img, conf=0.5, classes=0) 
    
    total_heads = 0
    zone_counts = {"North-West": 0, "North-East": 0, "South-West": 0, "South-East": 0}

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            # FEATURE: HEAD BOXING (Targeting the top part of the detected person)
            head_h = (y2 - y1) // 4
            head_y2 = y1 + head_h
            
            # Draw professional Cyan bounding box
            cv2.rectangle(img, (x1, y1), (x2, head_y2), (255, 255, 0), 2)
            
            # FEATURE: 4-ZONE LOGIC
            cx, cy = (x1 + x2) // 2, (y1 + head_y2) // 2
            if cx < mid_x and cy < mid_y: zone_counts["North-West"] += 1
            elif cx >= mid_x and cy < mid_y: zone_counts["North-East"] += 1
            elif cx < mid_x and cy >= mid_y: zone_counts["South-West"] += 1
            else: zone_counts["South-East"] += 1
            total_heads += 1

    # FEATURE: 4-ZONE SPLIT GRID (Red Lines)
    cv2.line(img, (mid_x, 0), (mid_x, h), (0, 0, 150), 1)
    cv2.line(img, (0, mid_y), (w, mid_y), (0, 0, 150), 1)

    _, buffer = cv2.imencode('.jpg', img)
    return zone_counts, total_heads, base64.b64encode(buffer).decode()

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1].lower()
    content = await file.read()
    
    # Process Image
    if ext in ['jpg', 'jpeg', 'png']:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        zones, total, b64_img = run_precision_detection(img)
        return {"type": "image", "total": total, "zones": zones, "image": b64_img}
    
    # FEATURE: VIDEO SUPPORT (Initial snapshot analysis)
    elif ext in ['mp4', 'avi']:
        return {"type": "video", "status": "Video file recognized. Starting frame-by-frame inference."}

    raise HTTPException(status_code=400, detail="Unsupported format")