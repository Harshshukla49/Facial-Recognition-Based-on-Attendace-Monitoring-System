import unittest
import numpy as np
from ai.matcher import FaceMatcher
from core.database import Database
from engine.attendance_engine import AttendanceEngine, AttendanceStatus

class TestBiometricDuplicateAndKiosk(unittest.TestCase):
    def setUp(self):
        self.matcher = FaceMatcher(duplicate_threshold=0.78)

    def test_duplicate_face_detection_across_different_students(self):
        # Generate an embedding for Student A
        emb_student_a = [0.1 * (i % 10) for i in range(128)]
        norm = np.linalg.norm(emb_student_a)
        emb_student_a = [float(x / norm) for x in emb_student_a]

        registered_templates = [
            {
                "student_id": "CSE2025012",
                "name": "Rahul Sharma",
                "embedding": emb_student_a
            }
        ]

        # New registration attempt for Student B with the SAME face (similarity = 1.0 > 0.78)
        is_dup, conflicting, sim_pct = self.matcher.check_duplicate_face(
            new_embedding=emb_student_a,
            registered_templates=registered_templates,
            current_student_id="CSE2025999"  # Different Student ID
        )

        self.assertTrue(is_dup)
        self.assertIsNotNone(conflicting)
        self.assertEqual(conflicting["student_id"], "CSE2025012")
        self.assertEqual(conflicting["name"], "Rahul Sharma")
        self.assertGreaterEqual(sim_pct, 99.0)

    def test_unique_face_allowed_when_no_match(self):
        emb_student_a = [1.0] + [0.0] * 127
        emb_student_b = [0.0] * 127 + [1.0]  # Orthogonal vector (similarity = 0.0)

        registered_templates = [
            {
                "student_id": "CSE2025012",
                "name": "Rahul Sharma",
                "embedding": emb_student_a
            }
        ]

        is_dup, conflicting, sim_pct = self.matcher.check_duplicate_face(
            new_embedding=emb_student_b,
            registered_templates=registered_templates,
            current_student_id="CSE2025013"
        )

        self.assertFalse(is_dup)
        self.assertIsNone(conflicting)

    def test_kiosk_confidence_rejection_below_85(self):
        # When confidence is 62% (< 85%), AttendanceEngine must return low_confidence
        res = AttendanceEngine.mark_attendance(
            student_id="51230249",
            confidence=62.0,  # Below 85% requirement
            liveness_verified=True,
            kiosk_id=1
        )
        self.assertFalse(res["marked"])
        self.assertEqual(res["status"], "low_confidence")
        self.assertIn("Verification Required", res["message"])

    def test_kiosk_spoof_rejection(self):
        # When liveness fails, AttendanceEngine must reject
        res = AttendanceEngine.mark_attendance(
            student_id="51230249",
            confidence=95.0,
            liveness_verified=False,  # Spoof detected
            kiosk_id=1
        )
        self.assertFalse(res["marked"])
        self.assertEqual(res["status"], "spoof_rejected")
        self.assertIn("Liveness Verification Failed", res["message"])

if __name__ == "__main__":
    unittest.main()
