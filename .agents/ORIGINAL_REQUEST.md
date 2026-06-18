# Original User Request

## 2026-06-17T16:21:07Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Rebuild ID photo main pipeline to be minimal, clean, and verifiable.

Rebuild the ID photo generation main pipeline into a minimal, clear, controllable, and verifiable chain by isolating legacy patches and focusing on core matting, lightweight alpha cleanup, face/shoulder-based cropping, and quality validation.

Working directory: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器`
Integrity mode: benchmark

## Requirements

### R1. Runtime Audit & Cache Clean
Audit the local `8000` service, ensure the correct engine and models are loaded, and clear all ID photo caches (temp, preview, download, requestId) without affecting other tools or user data.

### R2. Minimal ID Photo Pipeline
Isolate the legacy complex patch chain (e.g. into `server/id_photo_engine_legacy/`) and build a new minimal chain (`server/id_photo_engine_minimal/`) that consists of: Input validation -> Matting -> Check Alpha -> Lightweight alpha cleanup -> Crop -> Compose -> Check Quality.

### R3. Input Validation
Check if the photo is a single person, front face, clear, shoulders visible, etc. Reject invalid inputs with a clear prompt instead of force-processing.

### R4. Matting & Alpha First
Evaluate models via a unified adapter. The transparent PNG and alpha channel MUST be clean and complete (no severed shoulders, no missing clothes, no dark oval background). This is the first gate before cropping or background replacement.

### R5. Lightweight Cleanup & Crop
Only perform safe, lightweight alpha purification. Crop based on face box, eyes, head top, chin, and shoulder width for a 1-inch layout. Do not sever shoulders or shift the subject upward.

### R6. Quality Gate & Generalization
Rebuild quality checks. Any visible artifact (holes, background blobs, black panels, missing shoulders, edge lines) must FAIL. Verify against 30 random real positive samples and 10 negative samples. Generate zoom-in debug images.

### R7. WeChat & Flow Verification
Verify the entire chain in WeChat Developer tools. Confirm preview and download are consistent, use the same requestId, and have no artifacts. Run the full business flow tests to ensure no other tools were broken.

## Acceptance Criteria

### Pipeline & Cache
- [ ] Legacy patching code is isolated to a legacy folder/switch, not physically deleted.
- [ ] All uploaded photos get a new `requestId` and no old cached images are served.
- [ ] `runtime-chain-audit.md` and `cache-clean-report.md` are generated and accurate.

### Alpha Quality
- [ ] `transparent_png` has no missing shoulders, no holes in clothes, and no black/gray background patches.
- [ ] `alpha_channel` shows the main body is fully connected without huge gaps.
- [ ] `alpha-debug-report.md` and `zoom-quality-report.md` confirm clean alpha for all test samples.

### Generation & Cropping
- [ ] 1-inch crop is visually reasonable (correct head top margin, visible shoulders/chest) and doesn't chop off clothes arbitrarily.
- [ ] Five background colors synthesize cleanly without dark borders or background artifacts.

### Testing & Regression
- [ ] 30 random real positive samples and 10 negative samples tested; results documented.
- [ ] WeChat developer tools preview is visually clean and matches the downloaded image.
- [ ] All required npm verify scripts pass without fake/forced PASSes.

---

## Detailed Specification (User Directives)

一、本次最高限制
只允许修改证件照相关的上传、抠图、alpha边缘净化、裁剪、合成、缓存、验证脚本等主链路。
禁止修改首页、水印、排版、支付、云端等。禁止重构整站、假PASS、只检查接口等。不允许继续在旧复杂补丁链上叠补丁。

二、正确功能样本
参考样本质量标准：背景纯净、人像主体完整、头发边缘自然、无旧背景残留、透明前景干净、构图合理。必须额外使用随机真人照片验证泛化能力。

三、当前错误现象
肩膀被扣穿、衣服有缺口、后方有黑板残留、头发有蓝洞。这些说明 transparent/alpha 已经坏了，必须从头拦截。

四、本轮方向：隔离旧补丁链，重建最小闭环
把旧的复杂补丁逻辑（强修肩膀、修发丝洞等）隔离 to legacy。新的最小主链路必须是：检查合格性 -> 模型抠图 -> 检查透明图 -> 轻量净化 -> 裁剪 -> 五色底。如果透明图不干净，直接失败，不允许硬修。

五、先确认真实运行链路
停止并确认本地 8000 端口真实运行的文件，确认引擎、模型、requestId 等。生成 runtime-chain-audit.md 报告。

六、清理本地证件照缓存
停止进程，清理证件照 temp, foreground, preview, download 缓存。确保每次上传生成新 requestId，不允许复用旧图。

七、输入合格性检查
非单人、非正脸、严重侧脸、肩颈缺失的图片直接拦截并提示用户，不能强行生成。

八、transparent / alpha 必须作为第一验收点
生成 transparent_png 时，若发现衣服抠穿、黑板残留、主体断裂等肉眼可见脏块，直接 FAIL，不允许进入后续合成。生成 alpha-debug 报告。

九、主模型选择规则
优先测试 Hivision+rmbg-1.4, Hivision+birefnet 等。必须通过统一适配层隔离。选择 transparent 最干净、主体最完整的模型。

十、轻量 alpha 净化原则
只允许去除孤立噪点、分离的背景块、轻微羽化。禁止大范围强修肩膀、按颜色删背景等复杂后处理。

十一、裁剪构图规则
基于脸框、眼睛、头顶、下巴、肩膀宽度裁剪。禁止二次裁剪破坏主体或导致衣服被切掉。

十二、五色底合成规则
只负责合成，不负责拯救坏 foreground。preview 和 download 必须一致。

十三、质量检测重建
必须检测 alpha 完整性、黑色后板比例、边缘线条残留等。生成局部放大图检测。任何肉眼明显问题必须 FAIL。

十四、禁止用截图当原始上传图
必须从 server/uploads 找真实的原始上传照片进行正样本测试，不要把微信截图当原图跑。

十五、微信开发者工具真实验证
(由 Browser Agent 协作) 在微信开发者工具中走通全流程，确认前端预览无黑色椭圆、无蓝洞、无残缺，生成真实预览报告。

十六、随机泛化验证
找 30 张正样本（覆盖不同性别、衣服颜色、背景）和 10 张负样本验证。

十七、完整业务流回归
跑完 npm run verify:full-business-flow 等脚本，确保没影响去水印、排版等其它工具。

十八、最终报告
必须生成 15 份 Markdown 和 JSON 报告，写清当前模型、链路、测试结果、遗留问题。

十九、停止条件
上述 42 项要求必须全部满足、验证脚本真实 PASS 才能停止任务。

## Follow-up — 2026-06-18T12:23:14Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Fix ID photo generation quality (aliasing/jagged edges) and enforce Mainland China ID photo standards.

Update the ID photo generation pipeline (`server/id_photo_engine_minimal`) to output high-resolution, anti-aliased ID photos that strictly comply with Mainland China ID photo requirements (e.g., proper head ratio, pure background, no jagged edges). 

Working directory: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器`
Integrity mode: demo

## Requirements

### R1. Anti-Aliased High-Resolution Alpha
The current `alpha_cleanup.py` binarizes the alpha channel (`alpha > 127`), which destroys the soft edges from the matting model and causes severe jagged staircasing (aliasing). You must rewrite the cleanup logic to preserve the smooth alpha transitions (sub-pixel anti-aliasing) from the original matting output, while still removing isolated noise or disconnected background chunks.

### R2. Mainland China ID Photo Cropping Standard
The cropping logic (`crop.py`) must be updated to use facial detection/landmarks to intelligently scale and crop the photo. The subject's head (from chin to crown) should occupy approximately 2/3 of the photo height, and the face should be horizontally centered. The logic must prioritize keeping the shoulders visible and looking natural over strictly enforcing mathematical bounds if it causes awkward cuts.

### R3. Strict Isolation
Modifications must be isolated to the minimal ID photo engine (`server/id_photo_engine_minimal`). Do not touch unrelated features or cloud functionalities.

## Acceptance Criteria

### Edge Quality & Anti-Aliasing
- [ ] Visual inspection of the generated photo (especially hair and shoulder edges) shows smooth transitions without jagged pixelated staircases or hard white halos.
- [ ] Programmatic check: The alpha channel array contains a gradient of values (e.g., values between 10 and 245), proving it hasn't been hard-binarized.

### Proportion & Cropping
- [ ] The generated photo correctly centers the subject.
- [ ] The head height occupies roughly 2/3 of the total height (visually verified or programmatically measured).
- [ ] Shoulders remain naturally visible and are not arbitrarily cropped off.

### Regression Verification
- [ ] The existing test suite (`npm run verify` / `verify_id_photo_full_business_flow.py`) passes without regressions.
