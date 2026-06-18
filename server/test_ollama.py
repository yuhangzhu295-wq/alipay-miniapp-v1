# -*- coding: utf-8 -*-
import base64
import requests
import json
import time

TEST_IMAGE_PATH = r"C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\mockups\mockup_profile.png"

def test_ollama_vision(model_name):
    print(f"\nTesting Ollama vision model: {model_name}...")
    with open(TEST_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()
    
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    
    prompt = """Analyze this portrait image and determine if it is suitable for a professional ID/Passport photo.
Check these criteria:
1. Is there a face detected?
2. Is the lighting balanced?
3. Is the expression neutral/appropriate?
4. Is the head upright and pose correct?

Please output a JSON object in this EXACT format:
{
  "qualified": true or false,
  "score": a number from 0 to 100,
  "face_detected": true or false,
  "details": {
    "face_visibility": "description of face visibility",
    "background": "description of background",
    "lighting": "description of lighting",
    "pose": "description of pose"
  },
  "suggestions": ["suggestion 1", "suggestion 2"]
}
Only output the JSON object, nothing else. Do not wrap in markdown code blocks.
"""
    
    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "format": "json"
    }
    
    start_time = time.time()
    try:
        res = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=60)
        duration = time.time() - start_time
        print(f"Status Code: {res.status_code}")
        print(f"Time Taken: {duration:.2f} seconds")
        data = res.json()
        print("Response Text:")
        print(data.get("response"))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ollama_vision("moondream:latest")
    test_ollama_vision("minicpm-v:latest")
