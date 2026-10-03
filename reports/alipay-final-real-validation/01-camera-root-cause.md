# 01 相机根因分析（CAMERA）

## 用户现象

支付宝：直接拍摄 → 能进入相机页 → 能看到部分相机画面 → **点击快门不能真实完成拍摄**。

## 官方 API 契约差异（已核对支付宝文档）

```
微信：wx.createCameraContext()            // 无参数
支付宝：my.createCameraContext(cameraId)  // cameraId 必填，且必须与 <camera id> 一致
```

两者**不是同一契约**，不能简单等价替换。

## 根因（三处，同一缺陷）

| # | 位置 | 问题 |
| --- | --- | --- |
| 1 | `alipay/pages/id-camera/id-camera.axml` | `<camera>` **没有 id 属性** |
| 2 | `alipay/utils/platform/alipayWxCompat.js` | `my.createCameraContext()` **未传 cameraId** |
| 3 | `tools/alipay-migration/migrate.js` | 生成器丢掉了 id 与参数 → 每次重建都会复现 |

第 3 点很关键：只改产物会被下次 `npm run migrate:alipay` 覆盖，因此生成器必须一起修。

## 影响链

`<camera>` 无 id → `createCameraContext()` 拿不到相机组件 → `cameraContext.takePhoto()`
要么抛错要么无回调 → 无 `tempImagePath` → 相机模式停在 live，无法进入 confirm，
整条「拍照 → 使用照片 → prepare → compose」不可用。

## 分层

`CAMERA` + `ALIPAY_NATIVE_API`（不是 CANVAS，不是 UPLOAD，不是 BACKEND）

## 修复（仅支付宝侧，未改微信源码）

```diff
  <camera
+   id="idPhotoCamera"
    class="camera-view"
```

```diff
- createCameraContext: function() { ... my.createCameraContext() ... },
+ createCameraContext: function(cameraId) {
+   if (!platform.hasMy() || !my.createCameraContext) return null;
+   return my.createCameraContext(cameraId || 'idPhotoCamera');
+ },
```

生成器同步：`enhanceAlipayCameraMarkup()` 注入 id，适配器模板透传 cameraId。

## 变更文件

| 文件 | + | − |
| --- | --- | --- |
| `alipay/pages/id-camera/id-camera.axml` | 1 | 0 |
| `alipay/utils/platform/alipayWxCompat.js` | 6 | 1 |
| `tools/alipay-migration/migrate.js` | 19 | 2 |

分支：`fix/alipay-camera-cameraid-2026-10` @ `9361578`（本地，未 push）

