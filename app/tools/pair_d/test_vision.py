import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.tools.pair_d.vision import extract_best_frame, detect_issue
if len(sys.argv) < 2:
print("Usage: python test_vision.py /path/to/video.mp4")
sys.exit(1)
video = sys.argv[1]
print(f"\nTesting vision pipeline on: {video}")
print("[1/2] Extracting best frame ")
frame = extract_best_frame(video)
print(f" Saved: {frame}")
print("[2/2] Detecting issue ")
result = detect_issue(frame)
print(f" Label : {result['label']}")
print(f" Confidence: {result['confidence']}")
print("\nVision pipeline working correctly")