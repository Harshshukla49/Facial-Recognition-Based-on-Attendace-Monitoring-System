import datetime
from typing import List, Dict, Any, Optional
from core.database import Database

class EntryExitTracker:
    """Tracks student entry and exit events across campus/classroom cameras and calculates duration."""

    @staticmethod
    def log_event(student_id: str, camera_id: int, event_type: str, confidence: float = 95.0) -> Dict[str, Any]:
        """Logs an ENTRY or EXIT event for a student."""
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

        conn = Database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entry_exit_logs (student_id, camera_id, event_type, timestamp, confidence)
            VALUES (?, ?, ?, ?, ?)
        """, (student_id, camera_id, event_type, timestamp_str, confidence))

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "student_id": student_id,
            "event_type": event_type,
            "timestamp": timestamp_str
        }

    @staticmethod
    def get_student_presence_summary(student_id: str, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates first entry, last exit, and total active presence time on campus for a given date.
        """
        if not date_str:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")

        conn = Database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT event_type, timestamp, confidence 
            FROM entry_exit_logs
            WHERE student_id = ? AND timestamp LIKE ?
            ORDER BY timestamp ASC
        """, (student_id, f"{date_str}%"))

        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not logs:
            return {
                "student_id": student_id,
                "date": date_str,
                "entry_time": None,
                "exit_time": None,
                "total_duration_minutes": 0,
                "duration_formatted": "0h 0m",
                "events_count": 0
            }

        first_entry = next((l["timestamp"] for l in logs if l["event_type"] == "ENTRY"), logs[0]["timestamp"])
        last_exit = next((l["timestamp"] for l in reversed(logs) if l["event_type"] == "EXIT"), logs[-1]["timestamp"])

        try:
            t1 = datetime.datetime.strptime(first_entry, "%Y-%m-%d %H:%M:%S")
            t2 = datetime.datetime.strptime(last_exit, "%Y-%m-%d %H:%M:%S")
            diff_secs = max(0, int((t2 - t1).total_seconds()))
            hours = diff_secs // 3600
            mins = (diff_secs % 3600) // 60
            formatted = f"{hours}h {mins}m"
            total_mins = diff_secs // 60
        except Exception:
            formatted = "In Campus"
            total_mins = 0

        return {
            "student_id": student_id,
            "date": date_str,
            "entry_time": first_entry.split(" ")[1] if " " in first_entry else first_entry,
            "exit_time": last_exit.split(" ")[1] if " " in last_exit else last_exit,
            "total_duration_minutes": total_mins,
            "duration_formatted": formatted,
            "events_count": len(logs)
        }
