# 02 相机运行时验收（未完成，如实记录）

## 结论

```
CAMERA_TAKE_PHOTO_SUCCESS=UNKNOWN
CAMERA_CONFIRM_PASS=UNKNOWN
ALIPAY_CAMERA_E2E_PASS=false
```

按 §2「任何 UNKNOWN 都不能 PASS」，本轮**不声称相机已通过**。

## 已完成的验证

| 检查 | 结果 |
| --- | --- |
| AXML 含 `id="idPhotoCamera"` | ✅ |
| 适配器透传 cameraId（默认该 id） | ✅ |
| 生成器会重新注入 id（防回归） | ✅ |
| `verify:alipay-static` | ✅ 16/16 passed |
| `verify:alipay-builder` | ✅ exitCode=0, warningCount=0 |

这些只证明**代码与构建合法**，不证明相机能拍照（§36 禁止以构建成功冒充功能通过）。

## 未完成的原因

真实相机拍摄必须在**支付宝 IDE 模拟器或真机**执行。本会话：

- 没有可用的支付宝模拟器驱动通道；
- 支付宝 IDE 进程当前未运行（`小程序开发者工具` 无进程），且其登录态此前已确认需人工介入；
- 真机调试需要用户在支付宝开发者工具里发起（扫码/连真机）。

## 需要用户执行的一步

1. 打开支付宝开发者工具，加载 `alipay-miniapp-v1\alipay`；
2. 运行到「首页 → 一寸 → 直接拍摄」；
3. 观察：相机预览是否铺满、点击快门是否产出照片、是否进入确认页。

若模拟器不支持真实摄像头，必须按 §6 转真机调试。

## 我承诺的判定标准（待用户回报后填写）

```
CAMERA_PAGE_OPENED=
CAMERA_READY_EVENT=
CAMERA_CONTEXT_CREATED=
CAMERA_CONTEXT_BOUND=
SHUTTER_TAP_RECEIVED=
TAKE_PHOTO_CALLED=
TAKE_PHOTO_SUCCESS=
TAKE_PHOTO_FAIL=
TEMP_IMAGE_PATH=
CONFIRM_PAGE_RENDERED=
```

