# Model Warmup

- IOPaint is a persistent `systemd` service using LaMa on CPU; Backend never spawns a per-request model process.
- Startup model load: 589 ms on the measured deployment.
- Startup warmup: 96x96 image and mask, 974 ms on the first optimized start and 989 ms on the final 4-thread start.
- Warm requests report `modelLoaded=true`, `modelWarm=true`, and `modelLoadMs=0`.
- The warm state is tied to the current IOPaint PID through `/run/iopaint-lama-warm.json`.
- `Restart=on-failure` remains scoped to IOPaint.

Status: PASS.
