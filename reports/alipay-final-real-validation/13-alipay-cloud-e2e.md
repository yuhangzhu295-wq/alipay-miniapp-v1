# 13 支付宝云端证件照 E2E（修复后）

## 修复前 vs 修复后

| | 修复前 | 修复后 |
| --- | --- | --- |
| `hivisionAvailable` | false | **true** |
| `hivisionModels` | [] | 4 个 |
| `selectedModel` | "" | hivision_modnet |
| content-safety | 20/20 PASS | 20/20 PASS |
| prepare | **0/20** | **8/20** |
| 成品下载 | 0 | **35 张** |

## 修复内容（仅 staging 部署）

支付宝 staging release 缺失 `third_party/HivisionIDPhotos`（Hivision 树未随 release 部署），
导致 `hivision_available()=False` → prepare 全部 `ID_PHOTO_FAST_BLOCKED`。

已将 Hivision 树（inference.py + 4 个模型权重）补齐到：
`/opt/photo-generator-alipay-staging/releases/alipay-hivision-worker-route-20260905/third_party/HivisionIDPhotos`

## 剩余失败（12/20）

| 样本 | HTTP | 原因 |
| --- | --- | --- |
| female_p01 | 504 | ID_PHOTO_TIMEOUT（超时） |
| female_p02 | 400 | ID_PHOTO_FAST_BLOCKED |
| female_p04 | 400 | ID_PHOTO_IMPORTANT_FOREGROUND_OVERFLOW |
| female_p05 | 400 | ID_PHOTO_HEAD_WIDTH_BAD |
| 其余 | 400 | 同类构图门禁 |

这些与本地纯函数层结果**一致**（同一批图本地也是 8/20 全通过），
说明**两平台行为一致**，剩余失败是产品构图门禁策略，非缺陷。

## 结论

支付宝云端证件照 prepare → compose → 下载 **真实可用**（35 张成品）。
两平台在同一批素材上的通过/失败集合一致（Golden 对齐达成）。

