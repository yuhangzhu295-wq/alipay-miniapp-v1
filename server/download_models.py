# -*- coding: utf-8 -*-
import os
import sys
import numpy as np
import cv2
from PIL import Image
import tempfile
import asyncio

print("开始初始化云端 AI 模型环境...")
print("这可能会花费几分钟时间，请耐心等待下载完成。")

try:
    from id_photo_engine_minimal.matting import perform_matting
    from services.face_detector import detect_face
    
    # 1. 创建一张极小的纯色图片用于触发模型下载
    print("\n[1/4] 创建测试图像...")
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    dummy_img[:] = (200, 200, 200) # 灰色背景
    
    # 画一个类似人脸的圆，防止人脸检测完全崩溃
    cv2.circle(dummy_img, (50, 50), 20, (100, 150, 200), -1)
    
    _, img_encoded = cv2.imencode('.png', dummy_img)
    img_bytes = img_encoded.tobytes()
    
    # 2. 触发人脸检测模型下载 (Mediapipe)
    print("\n[2/4] 正在下载或加载人脸检测模型 (Mediapipe)...")
    try:
        detect_face(img_bytes)
        print(" -> 人脸检测模型加载完成！")
    except Exception as e:
        # 如果检测不到人脸报错也是正常的，这说明模型已经加载了
        print(" -> 人脸检测模型已调用。")

    # 3. 触发 Hivision Modnet 证件照模型下载
    print("\n[3/4] 正在下载或加载基础抠图模型 (Hivision Modnet)...")
    try:
        perform_matting(img_bytes, model="hivision_modnet")
        print(" -> 基础抠图模型加载完成！")
    except Exception as e:
        print(f" -> 基础抠图模型调用完成 (输出: {e})。")
        
    # 4. 触发 Birefnet 精修模型下载
    print("\n[4/4] 正在下载或加载发丝精修模型 (Birefnet v1 lite)...")
    try:
        perform_matting(img_bytes, model="birefnet-v1-lite")
        print(" -> 发丝精修模型加载完成！")
    except Exception as e:
        print(f" -> 发丝精修模型调用完成 (输出: {e})。")

    print("\n=============================================")
    print("所有核心证件照 AI 模型预热完毕！")
    print("=============================================")
    print("注意：去水印模型 (LaMa) 会在 start-hd-watermark-service.bat (或 IOPaint 命令) 启动时自动下载。")

except Exception as main_e:
    print(f"\n[错误] 初始化脚本遇到异常: {main_e}")
    sys.exit(1)
