import requests
import time

URL = "https://cleanbox-app-1.onrender.com"


def job():
    try:
        resp = requests.get(URL, timeout=10)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status: {resp.status_code}")
    except Exception as e:
        print(f"Error calling {URL}: {e}")


print("Starting loop: calling every 10 minutes.")
while True:
    job()
    time.sleep(600)  # 10분 = 600초
