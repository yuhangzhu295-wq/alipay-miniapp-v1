## ID Photo Generation Quality & Standards
When working on the ID photo generation pipeline, you must ALWAYS adhere to the following standards:
1. **High-Resolution Processing:** Never downscale the image drastically before matting or alpha cleanup. Processing must be done at a sufficient resolution (e.g., original size or min 1000px) to prevent aliasing (jagged edges) and white halos.
2. **Mainland China ID Photo Standards:** The cropping algorithm must ensure the subject is horizontally centered, and the head height (from chin to crown) occupies approximately 2/3 of the total photo height. 
3. **Anti-Aliasing:** Final resizing to print dimensions (e.g., 295x413) must use high-quality resampling (like LANCZOS) to maintain smooth, sharp edges.
