# 证件照生成器 — 后端 API 服务

## 安装与启动

```bash
cd server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

**注意：** rembg 首次运行会自动下载模型（~150MB），请耐心等待。后续使用不需要重新下载。

## 依赖项 (requirements.txt)

```
fastapi
uvicorn
python-multipart
pillow
rembg
onnxruntime
requests
opencv-python-headless
numpy
```

## API 列表

| 方法 | 端点 | 功能 | 依赖 |
|------|------|------|------|
| GET | `/api/health` | 健康检查 | — |
| POST | `/api/remove-bg` | AI 抠图（透明背景PNG） | rembg + onnxruntime |
| POST | `/api/change-bg` | 抠图 + 换底色 | rembg + Pillow |
| POST | `/api/inpaint` | AI 图像修复/去水印 | OpenCV Telea (本地) / IOPaint (可选) |
| POST | `/api/compress` | 目标 KB 压缩 | Pillow |
| POST | `/api/professional-photo` | 职业形象照模板合成 | Pillow |

## 开发环境配置

### 小程序端配置

在 `utils/apiConfig.js` 中：

```javascript
var API_BASE_URL = 'http://127.0.0.1:8000';  // 本地开发
var ENABLE_AI = true;
```

### 开发工具

微信开发者工具 → 详情 → 本地设置 → 勾选「不校验合法域名」

## 真机部署

真机调试/生产环境需要：

1. **HTTPS 域名** — 后端必须部署在有 HTTPS 证书的服务器上
2. **微信公众平台配置** — 开发管理 → 服务器域名：
   - `request` 合法域名：`https://你的域名`
   - `uploadFile` 合法域名：`https://你的域名`
   - `downloadFile` 合法域名：`https://你的域名`
3. **修改 API_BASE_URL** — `utils/apiConfig.js` 中的地址改为你的 HTTPS 域名
4. **API Key 安全** — 所有敏感密钥放后端环境变量，禁止写在小程序前端

## IOPaint 接入（可选，高质量 AI 去水印）

当前 `api/inpaint` 使用 OpenCV Telea 算法（基础修复）。如需更强的 AI inpainting 效果：

```bash
# 安装 IOPaint
pip install iopaint

# 启动 IOPaint 服务（默认端口 8080）
iopaint start --model lama --port 8080

# 设置环境变量切换模式
# Windows: set IOPAINT_URL=http://127.0.0.1:8080
# Linux/Mac: export IOPAINT_URL=http://127.0.0.1:8080
```

IOPaint 支持的模型：`lama`, `ldm`, `zits`, `mat`, `fcf`, `manga` 等。详见 [IOPaint 文档](https://www.iopaint.com/)。

## 接口详细说明

### POST /api/change-bg

```
入参：
  file: 图片文件 (multipart/form-data)
  bgColor: blue | white | red | lightBlue | gray

处理流程：
  1. rembg 移除背景 → 透明 PNG
  2. Pillow 创建目标底色背景
  3. 合成透明主体到底色背景
  4. 输出 JPG 结果

返回：
  { "success": true, "imageUrl": "/outputs/xxx.jpg" }
```

### POST /api/inpaint

```
入参：
  file: 原图
  x: 水印区域左上角 x (像素)
  y: 水印区域左上角 y (像素)
  width: 水印区域宽 (像素)
  height: 水印区域高 (像素)

处理流程：
  1. 根据 (x, y, width, height) 生成修复 mask
  2. OpenCV inpaint (Telea) 或 IOPaint 修复
  3. 返回修复后图片

返回：
  { "success": true, "imageUrl": "/outputs/xxx.jpg" }

失败：
  { "success": false, "message": "IOPaint 服务未配置或未启动" }
```

### POST /api/compress

```
入参：
  file: 原图
  targetKB: 目标文件大小 (KB)

处理：
  1. Pillow 循环降低 JPG quality (92 → 15)
  2. quality 到最低时缩小宽高 (每次 ×0.85)
  3. 返回最接近目标 KB 的图片

返回：
  { "success": true, "imageUrl": "/outputs/xxx.jpg", "targetKB": 40, "actualKB": 38.6 }
```

## AI 去水印 / 换底色 完整流程图

```
┌─────────────────┐      上传图片       ┌──────────────────┐
│   微信小程序      │ ─────────────────→ │   FastAPI 后端    │
│  前端 (Canvas)   │                     │   (Port 8000)    │
│                 │ ←─── 下载结果 ───── │                  │
│  显示 resultPath │                     │  rembg 抠图      │
│  保存到相册       │                     │  OpenCV inpaint  │
│  写入 PHOTO_RECORDS│                   │  Pillow 合成     │
└─────────────────┘                     └──────────────────┘
                                               │
                                        (可选) IOPaint
                                        更高质量修复
```

## License & 开源依赖

| 项目 | 用途 | License | 接入方式 |
|------|------|---------|----------|
| [rembg](https://github.com/danielgatis/rembg) | AI 抠图 | MIT | pip 安装 |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | rembg 模型推理 | MIT | pip 安装 |
| [IOPaint](https://github.com/Sanster/IOPaint) | AI 图像修复（可选） | Apache-2.0 | 独立服务调用 |
| [OpenCV](https://github.com/opencv/opencv) | 本地 inpainting | Apache-2.0 | pip opencv-python-headless |
| [Pillow](https://python-pillow.org/) | 图片处理 | Historical | pip 安装 |
| [FastAPI](https://github.com/tiangolo/fastapi) | Web 框架 | MIT | pip 安装 |

## 安全注意事项

- **API Key 不放前端** — rembg 不需要 API Key，IOPaint 也是本地运行
- **上传大小限制** — 建议限制在 10MB 以内
- **CORS** — 默认允许所有来源，生产环境请限制具体域名
- **文件清理** — outputs/ 目录定期清理，避免磁盘占满
