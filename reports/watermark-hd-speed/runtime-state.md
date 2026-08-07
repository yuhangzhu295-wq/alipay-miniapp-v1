# 高清去水印运行状态（修改前）

- 采集时间：2026-08-07 10:50 CST
- 生产域名：`https://tupzjianzhao.chat`
- 本地、GitHub `master`、腾讯云 SHA：均为 `63876c2b408d76c63fc952cd3170aa9ceea85687`
- Backend：`/root/photo-generator/server`，PID `2191106`，监听 `8000`
- IOPaint：`/root/photo-generator/server`，PID `1916966`，监听 `127.0.0.1:8081`
- IOPaint 命令：`/opt/iopaint-venv/bin/iopaint start --model=lama --device=cpu --port=8081`
- 模型/设备：真实 `lama` / CPU；进程从 2026-08-06 05:00 起常驻，修改前已运行约 29.8 小时
- Hivision Worker：PID `2192950`，监听 `127.0.0.1:8091`；本轮未修改、未重启
- CPU：4 核 AMD EPYC 7K62；内存 3.6 GiB，可用 2.3 GiB；Swap 5.9 GiB，已用 1.7 GiB
- IOPaint 进程：RSS 485.6 MiB、Swap 161.1 MiB、14 线程
- Nginx：`/` 代理到 `127.0.0.1:8000`，连接超时 10 秒，读写超时 360 秒

`/api/v1/model` 在 1.9ms 内返回 `lama`，同一个长驻进程连续服务请求，日志没有请求级模型下载、加载或新进程启动。修改前健康接口能证明模型已加载，但没有独立的 `modelWarm`、进程运行时间和最近预热耗时字段。

腾讯云工作树只有既有未跟踪备份目录 `backups/20260803-cloud/`；未改动它。
