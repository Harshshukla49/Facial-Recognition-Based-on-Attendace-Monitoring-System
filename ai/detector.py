import cv2
import numpy as np
import os
from typing import List, Tuple, Dict, Any, Optional
from config import Config

class FaceDetector:
    """Production face detector with image quality validation and normalization."""
    
    def __init__(self, cascade_path: Optional[str] = None):
        self.cascade_path = cascade_path or Config.HAAR_CASCADE_PATH
        if not os.path.isfile(self.cascade_path):
            raise FileNotFoundError(f"Haar cascade XML file not found at: {self.cascade_path}")
        self.detector = cv2.CascadeClassifier(self.cascade_path)

    def detect_faces(self, image_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detects multiple faces in the frame.
        Returns list of dicts: { 'box': (x, y, w, h), 'face_roi': gray_crop, 'quality': score }
        """
        if image_bgr is None or image_bgr.size == 0:
            return []

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        # Equalize histogram for robustness against illumination variations
        gray_eq = cv2.equalizeHist(gray)
        
        raw_faces = self.detector.detectMultiScale(
            gray_eq,
            scaleFactor=1.18,
            minNeighbors=5,
            minSize=Config.MIN_FACE_SIZE,
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        results = []
        for (x, y, w, h) in raw_faces:
            face_roi = gray[y:y + h, x:x + w]
            quality_score = self.evaluate_quality(face_roi, image_bgr[y:y+h, x:x+w])
            
            results.append({
                "box": (int(x), int(y), int(w), int(h)),
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "face_gray": face_roi,
                "face_bgr": image_bgr[y:y+h, x:x+w],
                "quality_score": quality_score
            })

        return results

    def evaluate_quality(self, face_gray: np.ndarray, face_bgr: np.ndarray) -> Dict[str, Any]:
        """Evaluates sharpness, brightness, and contrast of a face crop."""
        if face_gray is None or face_gray.size == 0:
            return {"score": 0.0, "is_valid": False, "reason": "Empty face region"}

        # 1. Sharpness (Laplacian variance)
        laplacian_var = cv2.Laplacian(face_gray, cv2.CV_64F).var()
        
        # 2. Brightness (Mean pixel value)
        mean_brightness = float(np.mean(face_gray))
        
        # 3. Contrast (Standard deviation)
        contrast = float(np.std(face_gray))

        is_sharp = laplacian_var >= 50.0
        is_lit = 40.0 <= mean_brightness <= 220.0
        has_contrast = contrast >= 25.0

        is_valid = is_sharp and is_lit and has_contrast
        score = min(100.0, max(10.0, (laplacian_var * 0.4) + (contrast * 0.4) + 20.0))

        reasons = []
        if not is_sharp:
            reasons.append("Image too blurry")
        if mean_brightness < 40:
            reasons.append("Lighting too dark")
        elif mean_brightness > 220:
            reasons.append("Lighting overexposed")
        if not has_contrast:
            reasons.append("Low contrast")

        return {
            "score": round(score, 1),
            "sharpness": round(laplacian_var, 1),
            "brightness": round(mean_brightness, 1),
            "contrast": round(contrast, 1),
            "is_valid": is_valid,
            "reason": ", ".join(reasons) if reasons else "Good quality"
        }
