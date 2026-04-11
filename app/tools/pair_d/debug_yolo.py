# app/tools/pair_d/debug_yolo.py
# shows EVERYTHING yolo detected — not just civic issues
from ultralytics import YOLO

model = YOLO('yolov8n.pt')
frame_path = "/tmp/best_frame.jpg"  # already saved from your last run

results = model(frame_path, verbose=False)[0]

if not results.boxes:
    print("YOLO detected: NOTHING in this frame")
    print("Try: darker video, too blurry, or extract a different frame")
else:
    print(f"YOLO detected {len(results.boxes)} objects:\n")
    for box in results.boxes:
        label = results.names[int(box.cls)]
        conf  = float(box.conf)
        print(f"  {label:20s}  confidence: {conf:.2f}")