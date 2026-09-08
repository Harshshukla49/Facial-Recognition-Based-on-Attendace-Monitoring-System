import datetime
import time
import sqlite3
from typing import Dict, Any, Optional, Tuple, List
from config import Config
from core.database import Database

class AttendanceStatus:
    PRESENT = "PRESENT"
    LATE = "LATE"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    EXCUSED = "EXCUSED"

class AttendanceEngine:
    """
    Enterprise Attendance State Machine.
    Evaluates timetable sessions, grace periods, late thresholds, duplicate cooldowns,
    and logs every camera detection as a separate Recognition Event for auditing.
    """
    
    # In-memory session recognition cache { (student_id, session_id): last_timestamp }
    _recognition_cooldowns: Dict[Tuple[str, int], float] = {}

    @classmethod
    def log_recognition_event(
        cls,
        student_id: Optional[str],
        kiosk_id: int,
        confidence: float,
        liveness_score: float,
        result: str,
        event_type: str = "KIOSK_SCAN"
    ):
        """Logs every camera recognition attempt into recognition_events table for auditing."""
        try:
            conn = Database.get_connection()
            conn.execute("""
                INSERT INTO recognition_events (student_id, kiosk_id, confidence, liveness_score, result, event_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (student_id, kiosk_id, confidence, liveness_score, result, event_type))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error logging recognition event: {e}")

    @classmethod
    def evaluate_attendance_status(
        cls, 
        arrival_dt: datetime.datetime, 
        session_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """Determines attendance status based on arrival time relative to class start."""
        if not session_info:
            return AttendanceStatus.PRESENT

        scheduled_start_str = session_info.get("scheduled_start", "")
        grace_period = int(session_info.get("grace_period_mins", Config.DEFAULT_GRACE_PERIOD_MINS))
        late_cutoff = int(session_info.get("late_cutoff_mins", Config.DEFAULT_LATE_CUTOFF_MINS))

        try:
            parts = scheduled_start_str.split(":")
            shour, smin = int(parts[0]), int(parts[1])
            sched_dt = arrival_dt.replace(hour=shour, minute=smin, second=0, microsecond=0)
            
            diff_mins = (arrival_dt - sched_dt).total_seconds() / 60.0

            if diff_mins <= grace_period:
                return AttendanceStatus.PRESENT
            elif diff_mins <= late_cutoff:
                return AttendanceStatus.LATE
            else:
                return AttendanceStatus.HALF_DAY
        except Exception:
            return AttendanceStatus.PRESENT

    @classmethod
    def mark_attendance(
        cls,
        student_id: str,
        confidence: float,
        liveness_verified: bool = True,
        liveness_score: float = 95.0,
        kiosk_id: int = 1
    ) -> Dict[str, Any]:
        """
        Processes an automatic kiosk face recognition event.
        Enforces confidence threshold (>= 85%), anti-spoofing, and database-level unique attendance.
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%d-%m-%Y")
        time_str = now.strftime("%H:%M:%S")

        # 1. Verification Requirement (Confidence Threshold Check)
        if confidence < Config.MIN_KIOSK_CONFIDENCE_THRESHOLD:
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "LOW_CONFIDENCE")
            return {
                "status": "low_confidence",
                "message": f"Verification Required: Recognition confidence ({confidence}%) is below required threshold ({Config.MIN_KIOSK_CONFIDENCE_THRESHOLD}%). Attendance not marked.",
                "student_id": student_id,
                "confidence": confidence,
                "marked": False
            }

        # 2. Liveness & Anti-Spoof Requirement
        if not liveness_verified:
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "SPOOF_REJECTED")
            return {
                "status": "spoof_rejected",
                "message": "Liveness Verification Failed: Potential spoof attempt (printed photo or screen) detected. Attendance not marked.",
                "student_id": student_id,
                "marked": False
            }

        conn = Database.get_connection()
        cursor = conn.cursor()

        # 3. Fetch student profile
        cursor.execute("SELECT id, student_id, full_name, class_id FROM students WHERE student_id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            conn.close()
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "UNKNOWN")
            return {"status": "error", "message": "Student not found in institutional registry", "marked": False}

        # 4. Fetch active session
        cursor.execute("""
            SELECT id, subject_name, room_number, scheduled_start, scheduled_end, grace_period_mins, late_cutoff_mins
            FROM attendance_sessions
            WHERE status = 'ACTIVE'
            ORDER BY id DESC LIMIT 1
        """)
        session = cursor.fetchone()
        session_id = session["id"] if session else None

        # 5. Check in-memory duplicate cooldown (5 minutes default)
        cooldown_key = (student_id, session_id or 0)
        last_marked_ts = cls._recognition_cooldowns.get(cooldown_key, 0.0)
        current_ts = time.time()

        if current_ts - last_marked_ts < Config.DUPLICATE_RECOGNITION_COOLDOWN_SECS:
            conn.close()
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "ALREADY_MARKED")
            return {
                "status": "already_marked",
                "message": f"Attendance already recorded for {student['full_name']} in this session.",
                "student_id": student_id,
                "student_name": student["full_name"],
                "marked": False
            }

        # 6. Database-Level Unique Constraint Check
        if session_id:
            cursor.execute("""
                SELECT id, status, time, date FROM attendance_records
                WHERE student_id = ? AND session_id = ? AND date = ?
            """, (student_id, session_id, date_str))
        else:
            cursor.execute("""
                SELECT id, status, time, date FROM attendance_records
                WHERE student_id = ? AND date = ?
            """, (student_id, date_str))

        existing_record = cursor.fetchone()
        if existing_record:
            cls._recognition_cooldowns[cooldown_key] = current_ts
            conn.close()
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "ALREADY_MARKED")
            return {
                "status": "already_marked",
                "message": f"Attendance Already Marked for {student['full_name']} ({existing_record['status']} at {existing_record['time']})",
                "student_id": student_id,
                "student_name": student["full_name"],
                "attendance_status": existing_record["status"],
                "marked_time": existing_record["time"],
                "marked": False
            }

        # 7. Evaluate Status (Present vs Late vs Half Day)
        status = cls.evaluate_attendance_status(now, dict(session) if session else None)

        # 8. Atomic Database Insert (Protected by Unique Constraint)
        try:
            cursor.execute("""
                INSERT INTO attendance_records 
                (session_id, student_id, date, time, status, confidence, liveness_verified, kiosk_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, student_id, date_str, time_str, status, confidence, 1, kiosk_id))
            
            # Log entry event
            cursor.execute("""
                INSERT INTO entry_exit_logs (student_id, camera_id, event_type, timestamp, confidence)
                VALUES (?, ?, 'ENTRY', ?, ?)
            """, (student_id, kiosk_id, f"{date_str} {time_str}", confidence))

            conn.commit()
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "MATCH_SUCCESS")
        except sqlite3.IntegrityError:
            # Race condition caught by unique constraint
            conn.rollback()
            conn.close()
            cls.log_recognition_event(student_id, kiosk_id, confidence, liveness_score, "ALREADY_MARKED")
            return {
                "status": "already_marked",
                "message": f"Attendance already recorded for {student['full_name']}",
                "student_id": student_id,
                "student_name": student["full_name"],
                "marked": False
            }

        conn.close()
        cls._recognition_cooldowns[cooldown_key] = current_ts

        return {
            "status": "success",
            "message": f"Welcome, {student['full_name']}! Attendance Marked: {status}",
            "student_id": student_id,
            "student_name": student["full_name"],
            "attendance_status": status,
            "time": time_str,
            "date": date_str,
            "confidence": confidence,
            "marked": True
        }
