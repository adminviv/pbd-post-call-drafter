#!/usr/bin/env python3
"""
Test script to find working Otter API endpoints.
Run this once to discover which endpoints return transcript data.
"""
import json
import requests
from otter_client import _load_cookies, HEADERS

session = requests.Session()
_load_cookies(session)

SHARE_ID = "1Llq6pqNctdQFH48Ep8fceeDYmE"

print("Testing Otter API endpoints...\n")

endpoints = [
    f"https://otter.ai/forward/user/get_speeches?page_size=5&source=",
    f"https://otter.ai/forward/user/get_speeches?page_size=5",
    f"https://otter.ai/forward/user/get_speech?share_id={SHARE_ID}",
    f"https://otter.ai/forward/user/speech_share?share_id={SHARE_ID}",
    f"https://otter.ai/forward/user/get_speech_share?share_id={SHARE_ID}",
    f"https://otter.ai/api/speech/share/{SHARE_ID}",
    f"https://otter.ai/forward/user/get_speech?otid={SHARE_ID}",
]

for url in endpoints:
    try:
        r = session.get(url, headers=HEADERS, timeout=10)
        body = r.text[:300].replace('\n', ' ')
        print(f"[{r.status_code}] {url}")
        if r.status_code == 200:
            print(f"  RESPONSE: {body}")
        print()
    except Exception as e:
        print(f"[ERR] {url} → {e}\n")
