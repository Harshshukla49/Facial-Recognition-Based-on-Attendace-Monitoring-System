import datetime
from typing import Dict, Any, List
from core.database import Database
from services.analytics_service import AnalyticsService

class AIAttendanceAssistant:
    """
    Grounded Natural Language AI Attendance Assistant.
    Parses natural language teacher/admin inquiries and answers strictly using factual database records.
    """

    @classmethod
    def query(cls, prompt: str) -> Dict[str, Any]:
        prompt_lower = prompt.lower().strip()
        conn = Database.get_connection()
        cursor = conn.cursor()
        today_str = datetime.datetime.now().strftime("%d-%m-%Y")

        answer = ""
        action_type = "GENERAL_INFO"
        data_payload = {}

        # 1. Query: Who is absent today?
        if "absent" in prompt_lower or "not present" in prompt_lower:
            cursor.execute("""
                SELECT s.student_id, s.full_name, c.name as class_name
                FROM students s
                LEFT JOIN classes c ON s.class_id = c.id
                WHERE s.student_id NOT IN (
                    SELECT student_id FROM attendance_records WHERE date = ?
                )
            """, (today_str,))
            absent_students = [dict(r) for r in cursor.fetchall()]
            
            if absent_students:
                lines = [f"- **{s['full_name']}** (`{s['student_id']}`) - {s.get('class_name', 'General')}" for s in absent_students]
                answer = f"📍 **{len(absent_students)} Students are Absent Today ({today_str}):**\n\n" + "\n".join(lines)
            else:
                answer = f"🎉 **Excellent! All enrolled students have marked attendance for today ({today_str}).**"
            
            action_type = "ABSENT_LIST"
            data_payload = {"count": len(absent_students), "students": absent_students}

        # 2. Query: Who came late today?
        elif "late" in prompt_lower or "delayed" in prompt_lower:
            cursor.execute("""
                SELECT ar.student_id, s.full_name, ar.time, ar.status
                FROM attendance_records ar
                JOIN students s ON ar.student_id = s.student_id
                WHERE ar.date = ? AND ar.status IN ('LATE', 'HALF_DAY')
                ORDER BY ar.time ASC
            """, (today_str,))
            late_students = [dict(r) for r in cursor.fetchall()]

            if late_students:
                lines = [f"- **{s['full_name']}** (`{s['student_id']}`) at `{s['time']}` ({s['status']})" for s in late_students]
                answer = f"⏰ **{len(late_students)} Students Arrived Late Today ({today_str}):**\n\n" + "\n".join(lines)
            else:
                answer = f"⏱ **No students arrived late today. All marked arrivals were within the scheduled grace period.**"

            action_type = "LATE_LIST"
            data_payload = {"count": len(late_students), "students": late_students}

        # 3. Query: Show students below 75%
        elif "75" in prompt_lower or "below threshold" in prompt_lower or "low attendance" in prompt_lower:
            low_list = AnalyticsService.get_students_below_threshold(75.0)
            if low_list:
                lines = [f"- **{s['name']}** (`{s['student_id']}`): **{s['percentage']}%** ({s['attended_days']}/{s['total_days']} days, Deficit: {s['deficit']}%)" for s in low_list]
                answer = f"⚠️ **{len(low_list)} Students are Below the 75% Mandatory Attendance Threshold:**\n\n" + "\n".join(lines)
            else:
                answer = "✅ **Great news! All enrolled students currently maintain attendance at or above the 75% requirement.**"

            action_type = "LOW_ATTENDANCE_LIST"
            data_payload = {"count": len(low_list), "students": low_list}

        # 4. Query: Today's attendance percentage / summary
        elif "percentage" in prompt_lower or "rate" in prompt_lower or "summary" in prompt_lower or "overview" in prompt_lower or "how many" in prompt_lower:
            summary = AnalyticsService.get_dashboard_summary()
            answer = (
                f"📊 **Attendance Intelligence Summary for Today ({today_str}):**\n\n"
                f"- **Total Enrolled Students:** {summary['total_students']}\n"
                f"- **Present Today:** {summary['present_today']} students\n"
                f"- **Late Arrivals:** {summary['late_today']} students\n"
                f"- **Absent Today:** {summary['absent_today']} students\n"
                f"- **Overall Attendance Rate:** **{summary['attendance_rate_percent']}%**\n"
                f"- **Low Attendance Risk (<75%):** {summary['low_attendance_count']} students\n"
                f"- **Active Online Cameras:** {summary['online_cameras']}"
            )
            action_type = "SUMMARY"
            data_payload = summary

        # 5. Query: Lowest attendance class / department
        elif "class" in prompt_lower or "department" in prompt_lower or "lowest" in prompt_lower or "highest" in prompt_lower:
            cursor.execute("""
                SELECT c.name as class_name, COUNT(ar.id) as attendances
                FROM classes c
                LEFT JOIN students s ON s.class_id = c.id
                LEFT JOIN attendance_records ar ON ar.student_id = s.student_id
                GROUP BY c.id
                ORDER BY attendances ASC
            """)
            classes_stats = [dict(r) for r in cursor.fetchall()]
            if classes_stats:
                lowest = classes_stats[0]
                highest = classes_stats[-1]
                answer = (
                    f"🏫 **Class Attendance Breakdown:**\n\n"
                    f"- **Highest Attendance Class:** **{highest['class_name']}** ({highest['attendances']} records)\n"
                    f"- **Lowest Attendance Class:** **{lowest['class_name']}** ({lowest['attendances']} records)"
                )
            else:
                answer = "No class-specific attendance records found."
            action_type = "CLASS_INSIGHTS"

        # Fallback general help
        else:
            answer = (
                f"🤖 **AI Attendance Assistant Ready.** You can ask me questions such as:\n\n"
                f"1. *\"Who is absent today?\"*\n"
                f"2. *\"Who came late today?\"*\n"
                f"3. *\"Show students below 75% attendance\"*\n"
                f"4. *\"What is today's attendance percentage?\"*\n"
                f"5. *\"Which class has the lowest attendance?\"*"
            )

        conn.close()
        return {
            "status": "success",
            "prompt": prompt,
            "answer": answer,
            "action_type": action_type,
            "data": data_payload
        }
