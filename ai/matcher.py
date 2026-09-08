import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from config import Config

class FaceMatcher:
    """
    Biometric Vector Matcher using Cosine Similarity and Euclidean Distance.
    Matches live query embeddings against enrolled encrypted student biometric templates
    and performs cross-student duplicate face conflict checks.
    """
    
    def __init__(
        self, 
        match_threshold: float = Config.FACE_MATCH_THRESHOLD,
        duplicate_threshold: float = Config.DUPLICATE_FACE_SIMILARITY_THRESHOLD
    ):
        self.match_threshold = match_threshold
        self.duplicate_threshold = duplicate_threshold

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculates cosine similarity between two normalized vectors (Range: -1.0 to 1.0)."""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-6 or norm_b < 1e-6:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def euclidean_distance(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculates Euclidean distance between two vectors."""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        return float(np.linalg.norm(a - b))

    def find_best_match(
        self, 
        query_embedding: List[float], 
        registered_templates: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[Dict[str, Any]], float]:
        """
        Finds the closest registered student template for the given face embedding.
        Returns: (is_matched: bool, best_student: dict or None, confidence_percent: float)
        """
        if not query_embedding or not registered_templates:
            return False, None, 0.0

        best_score = -1.0
        best_match = None

        for item in registered_templates:
            enrolled_emb = item.get("embedding")
            if not enrolled_emb:
                continue
            sim = self.cosine_similarity(query_embedding, enrolled_emb)
            if sim > best_score:
                best_score = sim
                best_match = item

        if best_score >= self.match_threshold and best_match is not None:
            # Map cosine score to intuitive 0-100% confidence
            confidence_pct = min(99.6, max(50.0, 75.0 + ((best_score - self.match_threshold) * 80.0)))
            return True, best_match, round(confidence_pct, 1)

        raw_conf = max(10.0, min(55.0, best_score * 70.0))
        return False, None, round(raw_conf, 1)

    def check_duplicate_face(
        self,
        new_embedding: List[float],
        registered_templates: List[Dict[str, Any]],
        current_student_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], float]:
        """
        Checks if the newly submitted face embedding biometrically matches ANY existing enrolled student.
        Prevents registering the same person under multiple Student IDs.
        Returns: (is_duplicate: bool, conflicting_student: dict or None, similarity_percent: float)
        """
        if not new_embedding or not registered_templates:
            return False, None, 0.0

        for item in registered_templates:
            sid = item.get("student_id")
            # Skip checking against the same student (e.g. when updating existing template)
            if current_student_id and str(sid) == str(current_student_id):
                continue

            enrolled_emb = item.get("embedding")
            if not enrolled_emb:
                continue

            sim = self.cosine_similarity(new_embedding, enrolled_emb)
            if sim >= self.duplicate_threshold:
                similarity_pct = round(sim * 100.0, 1)
                return True, item, similarity_pct

        return False, None, 0.0
