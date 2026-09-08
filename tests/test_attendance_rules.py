import unittest
import datetime
from engine.attendance_engine import AttendanceEngine, AttendanceStatus
from engine.entry_exit_tracker import EntryExitTracker

class TestAttendanceRules(unittest.TestCase):
    def test_on_time_arrival_evaluation(self):
        # Scheduled at 09:00, arrival at 09:05 (within 10m grace period)
        arrival = datetime.datetime(2026, 9, 8, 9, 5, 0)
        session = {
            "scheduled_start": "09:00",
            "grace_period_mins": 10,
            "late_cutoff_mins": 30
        }
        status = AttendanceEngine.evaluate_attendance_status(arrival, session)
        self.assertEqual(status, AttendanceStatus.PRESENT)

    def test_late_arrival_evaluation(self):
        # Scheduled at 09:00, arrival at 09:18 (exceeded 10m grace, within 30m cutoff)
        arrival = datetime.datetime(2026, 9, 8, 9, 18, 0)
        session = {
            "scheduled_start": "09:00",
            "grace_period_mins": 10,
            "late_cutoff_mins": 30
        }
        status = AttendanceEngine.evaluate_attendance_status(arrival, session)
        self.assertEqual(status, AttendanceStatus.LATE)

    def test_half_day_arrival_evaluation(self):
        # Scheduled at 09:00, arrival at 09:45 (exceeded 30m late cutoff)
        arrival = datetime.datetime(2026, 9, 8, 9, 45, 0)
        session = {
            "scheduled_start": "09:00",
            "grace_period_mins": 10,
            "late_cutoff_mins": 30
        }
        status = AttendanceEngine.evaluate_attendance_status(arrival, session)
        self.assertEqual(status, AttendanceStatus.HALF_DAY)

if __name__ == "__main__":
    unittest.main()
