import datetime
from typing import Dict, Any, List
from core.database import Database
from config import Config

class AnalyticsService:
    """AI Analytics & Attendance Intelligence Service."""

    @classmethod
    def get_dashboard_summary(cls) -> Dict[str, Any]:
        """Calculates comprehensive dashboard KPIs and overview metrics."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        today_str = datetime.datetime.now().strftime("%d-%m-%Y")

        # 1. Total Registered Students
        cursor.execute("SELECT COUNT(*) as count FROM students")
        total_students = cursor.fetchone()["count"]

        # 2. Today's Attendance Counts
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM attendance_records
            WHERE date = ?
            GROUP BY status
        """, (today_str,))
        
        status_counts = {"PRESENT": 0, "LATE": 0, "HALF_DAY": 0, "EXCUSED": 0, "ABSENT": 0}
        total_marked_today = 0
        for row in cursor.fetchall():
            st = row["status"]
            cnt = row["count"]
            status_counts[st] = cnt
            total_marked_today += cnt

        # Absent = Total Students - Total Marked Today
        calculated_absent = max(0, total_students - total_marked_today)
        status_counts["ABSENT"] = calculated_absent

        # Overall Today Attendance Rate
        present_and_late = status_counts["PRESENT"] + status_counts["LATE"] + status_counts["HALF_DAY"]
        attendance_rate = round((present_and_late / max(1, total_students)) * 100.0, 1)

        # 3. Students Below Threshold (e.g. < 75%)
        low_attendance_students = cls.get_students_below_threshold(threshold=Config.LOW_ATTENDANCE_THRESHOLD_PERCENT)

        # 4. Total Enrolled Biometric Profiles
        cursor.execute("SELECT COUNT(*) as count FROM biometric_templates")
        total_biometrics = cursor.fetchone()["count"]

        # 5. Total Active Cameras
        cursor.execute("SELECT COUNT(*) as count FROM cameras WHERE status = 'ONLINE'")
        online_cameras = cursor.fetchone()["count"]

        conn.close()

        return {
            "total_students": total_students,
            "total_marked_today": total_marked_today,
            "present_today": status_counts["PRESENT"],
            "late_today": status_counts["LATE"],
            "half_day_today": status_counts["HALF_DAY"],
            "absent_today": calculated_absent,
            "attendance_rate_percent": attendance_rate,
            "low_attendance_count": len(low_attendance_students),
            "biometrics_enrolled": total_biometrics,
            "online_cameras": online_cameras,
            "status_breakdown": status_counts
        }

    @classmethod
    def get_students_below_threshold(cls, threshold: float = 75.0) -> List[Dict[str, Any]]:
        """Identifies all students whose cumulative attendance percentage is below threshold."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT s.student_id, s.full_name, c.name as class_name, d.name as department_name,
                   COUNT(ar.id) as total_present,
                   (SELECT COUNT(DISTINCT date) FROM attendance_records) as total_working_days
            FROM students s
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN departments d ON s.department_id = d.id
            LEFT JOIN attendance_records ar ON s.student_id = ar.student_id AND ar.status IN ('PRESENT', 'LATE', 'HALF_DAY')
            GROUP BY s.student_id
        """)

        results = []
        for row in cursor.fetchall():
            working_days = max(1, row["total_working_days"] or 1)
            attended = row["total_present"] or 0
            percentage = round((attended / working_days) * 100.0, 1)

            if percentage < threshold:
                results.append({
                    "student_id": row["student_id"],
                    "name": row["full_name"],
                    "class_name": row["class_name"] or "General",
                    "department_name": row["department_name"] or "Engineering",
                    "attended_days": attended,
                    "total_days": working_days,
                    "percentage": percentage,
                    "deficit": round(threshold - percentage, 1)
                })

        conn.close()
        return sorted(results, key=lambda x: x["percentage"])

    @classmethod
    def get_attendance_trends(cls, days: int = 7) -> Dict[str, Any]:
        """Calculates past 7-day attendance trends for charts."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        # Get all distinct dates
        cursor.execute("""
            SELECT date, status, COUNT(*) as count
            FROM attendance_records
            GROUP BY date, status
            ORDER BY id DESC
            LIMIT 30
        """)

        data_map = {}
        for row in cursor.fetchall():
            d = row["date"]
            st = row["status"]
            cnt = row["count"]
            if d not in data_map:
                data_map[d] = {"date": d, "present": 0, "late": 0, "absent": 0}
            if st == "PRESENT":
                data_map[d]["present"] += cnt
            elif st in ["LATE", "HALF_DAY"]:
                data_map[d]["late"] += cnt

        conn.close()

        trend_list = list(data_map.values())[-days:] if data_map else [
            {"date": datetime.datetime.now().strftime("%d-%m-%Y"), "present": 5, "late": 1, "absent": 0}
        ]

        return {
            "trends": trend_list,
            "labels": [t["date"] for t in trend_list],
            "present_series": [t["present"] for t in trend_list],
            "late_series": [t["late"] for t in trend_list]
        }
