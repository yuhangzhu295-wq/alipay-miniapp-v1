# Resource Usage

- Host: 4 AMD EPYC 7K62 logical CPUs, 3.6 GiB RAM, 5.9 GiB configured Swap.
- Baseline old IOPaint: RSS about 485.6 MiB and process Swap about 161.1 MiB after long uptime.
- Fresh optimized 4-thread 20-run test: RSS 665.1 -> 764.2 MiB, process Swap 0 MiB, iowait delta 5 ticks.
- HD concurrency remains one task. Two simultaneous unique requests both passed; one reported `queueWaitMs=2426` while its LaMa inference stayed separately measured at 1604 ms.
- Two simultaneous identical request IDs produced one HTTP 200 and one HTTP 409 `HD_REQUEST_ACTIVE`.
- Hivision PID remained 2192950 through all IOPaint restarts.

Status: PASS.
