# ID Photo Real Speed Root Cause

## Baseline

- Date: 2026-08-05 (Asia/Shanghai)
- Production: `https://tupzjianzhao.chat`
- Production baseline: `c3f78a46ea198536a7a49ad18db4eddfb8f1466d`
- Mode: one-inch, `hairRetouch=false`
- Inputs: the three user-provided slow photos from the Windows desktop
- Runs: five per input, 15 total

| Input | Dimensions | Bytes | Runs | Client result |
| --- | ---: | ---: | ---: | --- |
| `6a83d1e010f6e9ed8c35af94f0c33936.jpg` | 960x1886 | 121027 | 5 | one 200 in 160738ms; four backend 504 responses near 181200ms |
| `610a7b3fadac6b4452736f72b8f3a492.jpg` | 1179x1526 | 209933 | 5 | five proxy 504 responses near 91000ms with non-JSON bodies |
| `217139c99959fa2888673f2100612b8f.jpg` | 1280x1707 | 325536 | 5 | one 200 in 183972ms; four backend 504 responses near 183970ms |

All 15 ordinary-mode requests exceeded the 30-second hard limit. The files are only 0.12-0.31MB, so upload size is not the primary cause.

## Confirmed Route

The first completed request (`54721311b8`) reported:

- FAST model: `hivision_modnet`
- FAST duration: 1870ms
- FAST inference: 989ms
- FAST queue wait: 0ms
- FAST failure: `ID_PHOTO_MATTING_BACKGROUND_LEAK`
- Automatic DETAIL: true despite `hairRetouch=false`
- DETAIL model: `birefnet-v1-lite`
- DETAIL duration: 156041ms
- DETAIL model load: 4163ms
- DETAIL inference: 82745ms
- Client total: 160738ms

The third input reproduced the same route in request `4a6d1d609e`: FAST 6494ms, automatic DETAIL 161820ms, total client 183972ms.

## Classification

- A upload preparation: not the primary cause; no work-copy step exists, but these inputs are already small.
- B `wx.uploadFile`: not isolated by the current client telemetry.
- C Nginx receive/proxy: confirmed secondary failure; one batch was terminated by the proxy at about 91 seconds before the backend's 180-second timeout.
- D backend save/decode: not isolated by the current server telemetry.
- E FAST model: not the root cause; the completed request ran FAST in 1.87 seconds.
- F automatic DETAIL: confirmed primary root cause.
- G queue wait: confirmed amplifier under concurrent requests. Timed-out `asyncio.to_thread` work continues after the HTTP response is cancelled.
- H compose: not involved in the reproduced delay because `/prepare` did not return.
- I result download/display: not involved in the reproduced delay because no result URL was available.

## Root Cause

`prepare_id_photo_v2` deletes the FAST result and synchronously calls `matte_person(... prefer_detail=True)` whenever the FAST quality probe blocks. This happens even when `hairRetouch=false`. On the 2C4G host, the isolated BiRefNet subprocess takes roughly 150-162 seconds. Backend cancellation does not stop the worker thread, so timed-out requests continue consuming CPU and the serialized inference lock. Proxy and backend timeout values are also inconsistent, producing non-JSON 504 responses and missing client request IDs.

No quality threshold was changed during baseline collection.
