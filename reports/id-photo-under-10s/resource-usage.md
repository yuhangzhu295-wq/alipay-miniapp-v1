# Cloud Resource Usage

- Host CPU: `AMD EPYC 7K62`, 4 vCPU deployment, 3723 MB RAM.
- Final Worker health snapshot: RSS `544.6 MB`, free memory `1988.6 MB`, load
  average `0.366`, both FAST sessions resident.
- Post-matrix host snapshot: memory used `1569 MB`, available `2153 MB`; swap
  used `1682 MB`. Linux retained previously swapped pages after the 30 DETAIL
  jobs, while more than 2 GB RAM remained available.
- Four post-load samples over 30 seconds held swap at exactly `1681 MB`; host
  available memory stayed between `2140 MB` and `2141 MB`. No monotonic growth
  was observed after the workload ended.
- `photo-generator`, `hivision-worker`, and `iopaint` were all `active`.
- Worker `DropInPaths` was empty; the temporary intra-op A/B override was removed.
- IOPaint was not restarted during the ID-photo deployment.

Status: **PASS**.
