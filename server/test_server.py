# -*- coding: utf-8 -*-
"""
后端 API 接口测试脚本 - 自动验证抠图、换底、水印修补和职业形象照
"""
import requests
import os

BASE_URL = "http://127.0.0.1:8000"
TEST_IMAGE_PATH = r"C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\mockups\mockup_profile.png"

def test_api():
    print("🚀 开始自动测试后端 AI 图像处理接口...\n")
    
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"❌ 错误: 未找到测试图片: {TEST_IMAGE_PATH}")
        return

    # 1. 健康检查
    print("1. [GET] /api/health - 健康检查...")
    try:
        res = requests.get(f"{BASE_URL}/api/health")
        print(f"   状态码: {res.statusCode if hasattr(res, 'statusCode') else res.status_code}")
        print(f"   响应内容: {res.json()}\n")
    except Exception as e:
        print(f"   ❌ 连接失败: {e}\n")
        return

    # 读取测试图片字节
    with open(TEST_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    # 2. AI 抠图
    print("2. [POST] /api/remove-bg - AI 抠图 (透明PNG)...")
    try:
        files = {"file": ("test.png", img_bytes, "image/png")}
        res = requests.post(f"{BASE_URL}/api/remove-bg", files=files)
        data = res.json()
        print(f"   状态码: {res.status_code}")
        print(f"   响应内容: {data}")
        if data.get("success"):
            print("   ✅ AI 抠图测试通过！")
        else:
            print("   ❌ AI 抠图失败！")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    print()

    # 3. AI 抠图 + 换底色
    print("3. [POST] /api/change-bg - AI 换底色 (合成新背景)...")
    try:
        files = {"file": ("test.png", img_bytes, "image/png")}
        data = {"bgColor": "blue"}
        res = requests.post(f"{BASE_URL}/api/change-bg", files=files, data=data)
        data = res.json()
        print(f"   状态码: {res.status_code}")
        print(f"   响应内容: {data}")
        if data.get("success"):
            print("   ✅ AI 换底色测试通过！")
        else:
            print("   ❌ AI 换底色失败！")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    print()

    # 4. AI 去水印 / 修复
    print("4. [POST] /api/inpaint - AI 去水印/修补...")
    try:
        files = {"file": ("test.png", img_bytes, "image/png")}
        data = {"x": "50", "y": "50", "width": "100", "height": "100"}
        res = requests.post(f"{BASE_URL}/api/inpaint", files=files, data=data)
        data = res.json()
        print(f"   状态码: {res.status_code}")
        print(f"   响应内容: {data}")
        if data.get("success"):
            print("   ✅ AI 去水印测试通过！")
        else:
            print("   ❌ AI 去水印失败！")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    print()

    # 5. 职业形象照 (新修复：先抠图再合成)
    print("5. [POST] /api/professional-photo - 职业形象照...")
    try:
        files = {"file": ("test.png", img_bytes, "image/png")}
        data = {"templateId": "blueSuit"}
        res = requests.post(f"{BASE_URL}/api/professional-photo", files=files, data=data)
        data = res.json()
        print(f"   状态码: {res.status_code}")
        print(f"   响应内容: {data}")
        if data.get("success"):
            print("   ✅ 职业形象照 AI 抠图融合测试通过！")
        else:
            print("   ❌ 职业形象照失败！")
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
    print()

    print("🎉 自动测试流程执行完毕！")

if __name__ == "__main__":
    test_api()
