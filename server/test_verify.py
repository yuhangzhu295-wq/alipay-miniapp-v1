# -*- coding: utf-8 -*-
import requests
import os
import json

BASE_URL = "http://127.0.0.1:8000"
TEST_IMAGE_PATH = r"C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\mockups\mockup_profile.png"

def test_verify_api():
    print("🚀 测试新接口 [POST] /api/verify-photo...")
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"❌ 无法找到测试图片: {TEST_IMAGE_PATH}")
        return

    with open(TEST_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    files = {"file": ("test.png", img_bytes, "image/png")}
    
    # Test moondream mode (faster)
    data = {"model": "moondream:latest"}
    try:
        print("发送请求到 /api/verify-photo (Moondream 模式)...")
        res = requests.post(f"{BASE_URL}/api/verify-photo", files=files, data=data, timeout=30)
        print(f"状态码: {res.status_code}")
        response_data = res.json()
        print("返回内容:")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))
        if response_data.get("success") and "checks" in response_data:
            print("✅ /api/verify-photo 接口测试成功！")
        else:
            print("❌ 接口返回异常！")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    test_verify_api()
