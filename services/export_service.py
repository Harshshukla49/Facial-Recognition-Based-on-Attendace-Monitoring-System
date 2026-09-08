import csv
import io
import datetime
from typing import List, Dict, Any, Optional
from core.database import Database

class ExportService:
    """Report Generation & Export Engine for CSV and structured reports."""

    @staticmethod
    def generate_attendance_csv(date_filter: Optional[str] = None, class_id: Optional[int] = None) -> str:
        """Generates a structured CSV report for attendance records."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT ar.date, ar.time, ar.status, ar.confidence, ar.liveness_verified,
                   s.student_id, s.full_name, c.name as class_name, d.name as department_name,
                   ar.is_manual_override, ar.override_reason
            FROM attendance_records ar
            JOIN students s ON ar.student_id = s.student_id
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN departments d ON s.department_id = d.id
            WHERE 1=1
        """
        params = []
        if date_filter:
            query += " AND ar.date = ?"
            params.append(date_filter)
        if class_id:
            query += " AND s.class_id = ?"
            params.append(class_id)

        query += " ORDER BY ar.date DESC, ar.time ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)

        # Header Metadata
        writer.writerow(["# Face Recognition Attendance Monitoring System - Official Audit Report"])
        writer.writerow(["# Generated At", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(["# Filter Date", date_filter or "ALL"])
        writer.writerow([])

        # Table Columns
        headers = [
            "Date", "Time", "Student ID", "Full Name", "Department", "Class",
            "Status", "Confidence (%)", "Liveness Verified", "Manual Override", "Override Reason"
        ]
        writer.writerow(headers)

        for r in rows:
            writer.writerow([
                r["date"],
                r["time"],
                r["student_id"],
                r["full_name"],
                r["department_name"] or "N/A",
                r["class_name"] or "N/A",
                r["status"],
                f"{r['confidence']:.1f}%",
                "YES" if r["liveness_verified"] else "NO",
                "YES" if r["is_manual_override"] else "NO",
                r["override_reason"] or ""
            ])

        return output.getvalue()
