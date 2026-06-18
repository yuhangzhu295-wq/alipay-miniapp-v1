## 2026-06-18T12:35:59Z
You are the Implementation Specialist. Your working directory is C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_implement_1.

MANDATORY INTEGRITY WARNING:
> DO NOT CHEAT. All implementations must be genuine. DO NOT
> hardcode test results, create dummy/facade implementations, or
> circumvent the intended task. A Forensic Auditor will independently
> verify your work. Integrity violations WILL be detected and your
> work WILL be rejected.

Your tasks:
1. Update `server/id_photo_engine_minimal/alpha_cleanup.py`:
   - Preserve soft alpha transitions by utilizing the connected components mask as a mask rather than hard binarizing the final alpha channel.
   - Implement color purification (interpolating colors for semi-transparent boundary pixels based on surrounding opaque pixels) to prevent halo bleeding. Look at `clean_refined_foreground_rgba` in `server/id_photo_engine_legacy/portrait_matting.py` for a reference implementation of this.
2. Update `server/id_photo_engine_minimal/crop.py`:
   - Accept a `face_res` dict argument. If face detection data is available:
     - If landmarks (leftEye, rightEye) are available, calculate face center and estimate head scale.
     - Else if only faceBox is available, calculate based on faceBox center and scale.
     - Else fall back to standard bounding box cropping.
   - Crop the subject so the face is horizontally centered, and the head height (chin to crown) occupies approximately 2/3 of the total photo height.
   - Handle border conditions safely by padding the image with transparent pixels prior to cropping, ensuring no awkward cuts of shoulders or head.
3. Update `server/id_photo_engine_minimal/api.py`:
   - Retrieve the face detection result `face_res = detect_face(img_bytes)` in `generate_id_photo_v2` and `prepare_id_photo_v2`.
   - Pass `face_res` to `crop_id_photo(rgba, w, h, face_res=face_res)`.
4. Verification:
   - Test your changes locally. Run the relevant verification scripts (e.g., `npm run verify:id-photo-quality` or `npm run verify:id-photo-main-flow`) to ensure they compile and work.
5. Write your handoff report to C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_implement_1\handoff.md.

Communicate your completion back by sending a message to the caller.
