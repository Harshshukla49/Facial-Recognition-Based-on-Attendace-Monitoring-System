import cv2
import numpy as np
from typing import Dict, Any, Tuple
from config import Config

class LivenessDetector:
    """
    Multi-Metric Active and Passive Anti-Spoofing & Liveness Verification Engine.
    Detects paper printouts, phone screen replays, and static images.
    """
    
    def __init__(self, blur_threshold: float = Config.LIVENESS_BLUR_THRESHOLD):
        self.blur_threshold = blur_threshold

    def check_liveness(self, face_bgr: np.ndarray, face_gray: np.ndarray) -> Dict[str, Any]:
        """
        Runs comprehensive liveness & anti-spoofing checks on a detected face crop.
        Returns: { 'is_live': bool, 'confidence': float, 'metrics': {...}, 'reason': str }
        """
        if face_gray is None or face_gray.size == 0 or face_bgr is None:
            return {"is_live": False, "confidence": 0.0, "reason": "No face pixels"}

        # 1. Texture & Frequency Variance Check (Laplacian High-Frequency Analysis)
        laplacian = cv2.Laplacian(face_gray, cv2.CV_64F)
        texture_variance = float(laplacian.var())

        # 2. Color Chroma Distribution (Screens usually have distorted saturation/specular hotspots)
        hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        sat_mean = float(np.mean(s))
        val_std = float(np.std(v))

        # 3. Fourier Frequency Energy Analysis (Moiré pattern detection)
        dft = cv2.dft(np.float32(face_gray), flags=cv2.DFT_COMPLEX_OUTPUT)
        dft_shift = np.fft.fftshift(dft)
        magnitude_spectrum = 20 * np.log(cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1]) + 1e-5)
        high_freq_energy = float(np.mean(magnitude_spectrum))

        # Combine checks
        is_natural_texture = texture_variance >= 65.0
        is_natural_lighting = 20.0 <= sat_mean <= 220.0 and val_std >= 20.0
        is_natural_spectrum = high_freq_energy >= 80.0

        score = 0.0
        if is_natural_texture:
            score += 45.0 * min(1.0, texture_variance / 150.0)
        if is_natural_lighting:
            score += 35.0
        if is_natural_spectrum:
            score += 20.0

        is_live = (texture_variance >= 60.0) and (score >= 60.0)

        reason = "Real Person Verified ✓" if is_live else "Anti-Spoof Warning: Potential photo or digital screen detected"

        return {
            "is_live": is_live,
            "confidence": round(min(99.0, max(10.0, score)), 1),
            "texture_variance": round(texture_variance, 1),
            "saturation_mean": round(sat_mean, 1),
            "frequency_energy": round(high_freq_energy, 1),
            "reason": reason
        }
