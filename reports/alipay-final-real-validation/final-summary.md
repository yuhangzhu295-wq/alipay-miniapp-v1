# 支付宝小程序全功能自动巡检 — 阶段总结

- 日期：2026-10-04 (Asia/Shanghai)
- 支付宝分支：`fix/alipay-camera-cameraid-2026-10` @ `9361578`（本地，**未 push**）
- 微信 master：`5c696b9a93866b361851940095610b67a670870c`（**未改动**）

## 本轮完成的核心修复（CAMERA）

**根因**：支付宝 `my.createCameraContext(cameraId)` 必须传 cameraId，与微信
`wx.createCameraContext()` 契约不同；迁移时该参数被丢弃，且 `<camera>` 没有 id，
导致快门无法真实拍摄。

**修复**（仅支付宝侧）：
1. `<camera>` 增加 `id="idPhotoCamera"`
2. 适配器 `createCameraContext(cameraId)` 透传并默认该 id
3. 迁移生成器同步注入 id 与参数（防止重建复现）

## 严格遵守的限制

| 限制 | 状态 |
| --- | --- |
| 未修改微信项目 | ✅ |
| 未修改证件照算法 / Hivision / BiRefNet / LaMa | ✅ |
| 未修改质量阈值 / 规格 | ✅ |
| 未 push | ✅（按 §42） |
| 未 merge / 未部署 / 未重启生产 | ✅ |

## 过程中的自我纠错（重要）

我最初用 `npm run migrate:alipay` 重新生成整个 `alipay/`，`git diff` 显示 **19 文件、670 行删除**，
说明已提交的 `alipay/` 含有生成器之外的人工修复（如 camera 的动态尺寸 style、
`controlsHeightPx`）。这会**冲掉既有修复**，违反「不要重新迁移」。

我已 `git checkout -- alipay/` 完全回退，改用**最小外科式修改**（3 文件、+26/−3），
只动必要的两处 + 生成器。

## 未完成 / 阻塞

| 项 | 状态 | 原因 |
| --- | --- | --- |
| 相机真机/模拟器拍摄 | **UNKNOWN** | 无可用支付宝模拟器驱动通道；需用户发起 |
| 男女各 5 张真实业务 | 未执行 | 依赖 GUI 通道（§13 要求走应用入口） |
| 五色底 / A-B 对比 / 图片工具 GUI | 未执行 | 同上 |
| 真机 UI 截图 | 未执行 | 同上 |

## 明确不做的假 PASS

按 §36，以下**不**作为功能通过：构建成功、静态检查通过、页面能打开、handler 存在。
因此本轮 `ALIPAY_RUNTIME_REAL_PASS=false`、`FULL_PARITY_PASS=false`。

## 需要用户执行的一步（解除阻塞）

打开**支付宝开发者工具**，加载 `alipay-miniapp-v1\alipay`，并运行到相机页；
如需真机，请发起真机调试。完成后回复「已就绪」，我立即继续执行：

相机 E2E → 男女各 5 张 → 微信 Golden 同图 → 五色底 → 发丝精修 → 去水印/工具 → 登录隔离 → 全产品 GUI 回归 → 最终报告。

## 附：腾讯云侧的修复（上一轮，已生效）

支付宝 staging 的 `third_party/HivisionIDPhotos` 缺失导致 `hivisionAvailable=false`，
`ID_PHOTO_FORCE_HIVISION` 又把它掩盖成 ready。已补齐 Hivision 树（仅 staging），
本地验证 `hivision_available()=(True,'installed')`；服务重启验证因终端会话断开未完成。

## 追加：支付宝云端证件照 E2E 已打通

staging 修复后经公网 HTTPS 复测（20 张真实素材）：

```hivisionAvailable=true（4 个模型）```、content-safety 20/20 PASS、
prepare **8/20 通过**、**35 张真实云端证件照成品下载**。

剩余 12 张失败与本地纯函数层结果一致（同一批图本地也是 8/20），
即两平台行为一致，剩余失败为产品构图门禁策略而非缺陷。

详见 `13-alipay-cloud-e2e.md`。
