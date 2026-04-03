import cv2
import os
from ultralytics import YOLO
from smolagents import tool
model = YOLO('yolov8n.pt')
ISSUE_MAP = {
'bottle': 'garbage',
'cup': 'garbage',
'handbag': 'garbage',
'backpack': 'garbage',
'suitcase': 'garbage',
'dining table': 'garbage',
'car': 'road_blockage',
'truck': 'road_blockage',
'motorcycle': 'road_blockage',
'bus': 'road_blockage',
'cow': 'stray_animal',
'dog': 'stray_animal',
'cat': 'stray_animal',
'bench': 'infrastructure',
}
def _sharpness(frame):
"""Score frame sharpness — higher = clearer image."""
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
return cv2.Laplacian(gray, cv2.CV_64F).var()
@tool
def extract_best_frame(video_path: str) -> str:
"""
Extract the sharpest frame from a video file.
Samples frames at 20%, 50%, and 80% of video duration.
Picks the sharpest one using Laplacian variance scoring.
Args:
video_path: full path to the video file (.mp4 or any format)
Returns:
path to saved JPEG frame at /tmp/best_frame.jpg
"""
if not os.path.exists(video_path):
raise FileNotFoundError(f"Video not found: {video_path}")
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
raise ValueError(f"Cannot open video: {video_path}")
total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
if total_frames < 1:
cap.release()
raise ValueError("Video has no readable frames")
best_frame, best_score = None, -1
for pct in [0.2, 0.5, 0.8]:
cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pct))
ret, frame = cap.read()
if not ret:
continue
score = _sharpness(frame)
if score > best_score:
best_score, best_frame = score, frame.copy()
cap.release()
if best_frame is None:
raise ValueError("Could not extract any frame from video")
out_path = "/tmp/best_frame.jpg"
cv2.imwrite(out_path, best_frame)
return out_path
@tool
def detect_issue(frame_path: str) -> dict:
"""
Run YOLOv8 object detection on a frame.
Maps detected objects to civic issue categories.
Args:
frame_path: path to JPEG image file
Returns:
dict with keys: label (str), confidence (float 0.0-1.0)
"""
if not os.path.exists(frame_path):
return {"label": "unknown", "confidence": 0.0}
results = model(frame_path, verbose=False)[0]
detections = []
for box in results.boxes:
label = results.names[int(box.cls)]
conf = float(box.conf)
issue = ISSUE_MAP.get(label)
if issue:
detections.append({
"label": issue,
"confidence": round(conf, 3)
})
if not detections:
return {"label": "unknown", "confidence": 0.0}
return max(detections, key=lambda x: x["confidence"])