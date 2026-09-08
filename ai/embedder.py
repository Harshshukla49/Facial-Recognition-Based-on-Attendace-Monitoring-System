import cv2
import numpy as np
from typing import List, Optional
from config import Config

class FaceEmbedder:
    """
    Modular Face Biometric Embedding Extractor.
    Generates 128-dimensional normalized unit vectors representing facial feature landmarks.
    """
    
    def __init__(self, target_size: tuple = (112, 112), embedding_dim: int = 128):
        self.target_size = target_size
        self.embedding_dim = embedding_dim

    def extract_embedding(self, face_gray: np.ndarray) -> Optional[List[float]]:
        """
        Extracts a normalized 128-D biometric embedding vector from a cropped grayscale face.
        Uses multi-region spatial gradient histograms & frequency pooling with L2 normalization.
        """
        if face_gray is None or face_gray.size == 0:
            return None

        # Resize to standard canonical size
        resized = cv2.resize(face_gray, self.target_size, interpolation=cv2.INTER_AREA)
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(resized)

        # Multi-scale grid pooling (4x4 spatial cells)
        cells_x, cells_y = 4, 4
        h, w = enhanced.shape
        cell_h, cell_w = h // cells_y, w // cells_x
        
        feature_parts = []
        for r in range(cells_y):
            for c in range(cells_x):
                cell = enhanced[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w]
                # Calculate Sobel gradients in X and Y
                gx = cv2.Sobel(cell, cv2.CV_32F, 1, 0, ksize=3)
                gy = cv2.Sobel(cell, cv2.CV_32F, 0, 1, ksize=3)
                mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
                
                # 8-bin orientation histogram per cell
                hist, _ = np.histogram(ang, bins=8, range=(0, 360), weights=mag)
                feature_parts.extend(hist.tolist())

        # 4 * 4 * 8 = 128 dimensions
        vector = np.array(feature_parts, dtype=np.float32)
        
        # L2-Norm normalization to project onto a unit hypersphere
        norm = np.linalg.norm(vector)
        if norm > 1e-6:
            vector = vector / norm
        else:
            vector = np.zeros(self.embedding_dim, dtype=np.float32)

        return [round(float(x), 5) for x in vector[:self.embedding_dim]]

    def extract_multi_angle_average(self, face_crops: List[np.ndarray]) -> Optional[List[float]]:
        """Averages multiple face embeddings from varied angles (frontal, left, right) into a unified master template."""
        valid_embeddings = []
        for crop in face_crops:
            emb = self.extract_embedding(crop)
            if emb is not None:
                valid_embeddings.append(np.array(emb, dtype=np.float32))

        if not valid_embeddings:
            return None

        avg_vector = np.mean(valid_embeddings, axis=0)
        norm = np.linalg.norm(avg_vector)
        if norm > 1e-6:
            avg_vector = avg_vector / norm

        return [round(float(x), 5) for x in avg_vector[:self.embedding_dim]]
