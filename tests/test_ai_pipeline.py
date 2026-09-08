import unittest
import numpy as np
import cv2
from ai.detector import FaceDetector
from ai.embedder import FaceEmbedder
from ai.liveness import LivenessDetector
from ai.matcher import FaceMatcher

class TestAIPipeline(unittest.TestCase):
    def setUp(self):
        self.detector = FaceDetector()
        self.embedder = FaceEmbedder()
        self.liveness = LivenessDetector()
        self.matcher = FaceMatcher()

    def test_embedding_dimensions_and_normalization(self):
        # Create a synthetic face-like image (100x100)
        synth_face = np.random.randint(50, 200, (100, 100), dtype=np.uint8)
        vector = self.embedder.extract_embedding(synth_face)
        
        self.assertIsNotNone(vector)
        self.assertEqual(len(vector), 128)
        # Verify L2 norm is approximately 1.0
        norm = np.linalg.norm(np.array(vector))
        self.assertAlmostEqual(norm, 1.0, places=3)

    def test_cosine_similarity_identical_vectors(self):
        vec_a = [0.1 * i for i in range(128)]
        norm_a = np.linalg.norm(vec_a)
        vec_a = [x / norm_a for x in vec_a]
        
        sim = self.matcher.cosine_similarity(vec_a, vec_a)
        self.assertAlmostEqual(sim, 1.0, places=4)

    def test_liveness_detection_on_solid_image(self):
        # Uniform solid flat image represents flat photo/spoof without human texture
        solid_crop_gray = np.full((100, 100), 128, dtype=np.uint8)
        solid_crop_bgr = np.full((100, 100, 3), 128, dtype=np.uint8)
        
        result = self.liveness.check_liveness(solid_crop_bgr, solid_crop_gray)
        self.assertFalse(result["is_live"])
        self.assertIn("Anti-Spoof Warning", result["reason"])

if __name__ == "__main__":
    unittest.main()
