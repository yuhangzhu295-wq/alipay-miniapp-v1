## ID Photo Generation Quality & Standards
When working on the ID photo generation pipeline, you must ALWAYS adhere to the following standards:
1. **High-Resolution Processing:** Never downscale the image drastically before matting or alpha cleanup. Processing must be done at a sufficient resolution (e.g., original size or min 1000px) to prevent aliasing (jagged edges) and white halos.
2. **Mainland China ID Photo Standards:** The cropping algorithm must ensure the subject is horizontally centered, and the head height (from chin to crown) occupies approximately 2/3 of the total photo height. 
3. **Anti-Aliasing:** Final resizing to print dimensions (e.g., 295x413) must use high-quality resampling (like LANCZOS) to maintain smooth, sharp edges.

<RULE[id_photo_crop_standards]>
# 中国大陆证件照构图标准 (Chinese ID Photo Crop Standards)

When modifying image cropping, alignment, or layout logic in this project, you MUST strictly enforce the following visual proportions:

1. **Head Proportion (头部占比)**: The vertical height of the head (from the bottom of the chin to the top of the hair) MUST occupy strictly between **65% and 75%** (target 70%) of the total photo height.
2. **Top Margin (头顶留白)**: There MUST be a visible gap between the top of the hair and the top edge of the photo. For a 35mm photo, this is about 3-5mm (roughly 8-12% of the photo height). The hair must never touch the top edge.
3. **Horizontal Alignment (水平居中)**: The face MUST be perfectly centered horizontally, with equal empty space on both sides.
4. **Bottom Margin (肩膀裁切)**: The crop MUST preserve the shoulders. Both shoulders and the clavicle area must be completely visible. The crop must not prematurely truncate the subject's torso or leave the head floating too low in the frame.
5. **Universal Application**: This standard applies to ALL formats (e.g., one-inch, two-inch, ID card) unless a specific format explicitly overrides it.

**Quick Validation Rule**: "头顶留一点，下巴空一截；头占画面三分之二，双肩完整露出来；人脸居中不贴边" (Leave space at the top, leave space at the bottom; head takes two-thirds, shoulders fully visible; face centered).
</RULE[id_photo_crop_standards]>

<RULE[id_photo_matting_engine]>
# Matting Engine Selection

When performing matting for ID photos, ALWAYS prioritize `birefnet-v1-lite` as the primary model. Avoid using `rmbg-1.4` or generic `modnet` for the final ID photo product, as they leave background artifacts inside hair gaps. `birefnet-v1-lite` performs best for these cases.
</RULE[id_photo_matting_engine]>

<RULE[flowing_hair_matting]>
# Flowing Hair Matting

When dealing with flowing hair (飘散长发) and complex neck/shoulder gaps in ID photos, do NOT use hard color thresholds (which cause halos). Instead, rely on specialized matting models or advanced guided-filter alpha refinement.
</RULE[flowing_hair_matting]>
