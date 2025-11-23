# stream.py (headless capture)
import cv2, time, os, json
from datetime import datetime

# ---- SET PHONE IP HERE (IP Webcam) ----
PHONE_IP = "10.154.201.1"                 # <-- replace with your phone IP if different
STREAM_URL = f"http://{PHONE_IP}:8080/video"   # /video works for many IP Webcam configs
# ---------------------------------------

OUT_DIR = "captures"
N_SECONDS = 2.0   # capture interval
MAX_FAILED = 30

os.makedirs(OUT_DIR, exist_ok=True)
INDEX = os.path.join(OUT_DIR, "index.json")

# load or init index
if os.path.exists(INDEX):
    try:
        frames = json.load(open(INDEX))
    except:
        frames = []
else:
    frames = []

def safe_write_index():
    tmp = INDEX + ".tmp"
    with open(tmp, "w") as f:
        json.dump(frames, f, indent=2)
    os.replace(tmp, INDEX)

print("Opening stream:", STREAM_URL)
cap = cv2.VideoCapture(STREAM_URL)
time.sleep(1)

if not cap.isOpened():
    print("❌ Cannot open IP Webcam stream. Open the URL in your browser to confirm:")
    print(STREAM_URL)
    raise SystemExit(1)

print("✅ Stream opened. Headless capture every", N_SECONDS, "seconds. Use Ctrl+C to stop.")
last = 0.0
failed = 0
saved = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            failed += 1
            if failed % 10 == 0:
                print(f"⚠️ Frame failed {failed} times — retrying...")
            if failed > MAX_FAILED:
                print("⚠️ Reconnecting...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(STREAM_URL)
                failed = 0
            time.sleep(0.1)
            continue

        failed = 0
        now = time.time()
        if now - last >= N_SECONDS:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            fname = f"img_{ts}.jpg"
            path = os.path.join(OUT_DIR, fname)
            ok = cv2.imwrite(path, frame)
            if ok:
                frames.append({"filename": fname, "utc": datetime.utcnow().isoformat()+"Z"})
                safe_write_index()
                saved += 1
                print(f"💾 Saved ({saved}): {fname}")
            else:
                print("❌ Failed to write image.")
            last = now
        time.sleep(0.01)
except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    cap.release()
    print("Exiting. Total saved:", saved)
