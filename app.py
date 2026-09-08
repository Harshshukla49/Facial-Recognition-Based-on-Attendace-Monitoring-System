import os
import cv2
import base64
import json
import io
import datetime
import time
from typing import Optional, Dict, List, Any, Tuple
import numpy as np
from PIL import Image
from flask import Flask, render_template, request, jsonify, send_file, Response, g

from config import Config
from core.database import Database
from core.security import SecurityService
from core.rbac import Role, require_auth, get_current_user
from ai.detector import FaceDetector
from ai.embedder import FaceEmbedder
from ai.liveness import LivenessDetector
from ai.matcher import FaceMatcher
from engine.attendance_engine import AttendanceEngine, AttendanceStatus
from engine.entry_exit_tracker import EntryExitTracker
from engine.offline_sync import OfflineSyncEngine
from services.analytics_service import AnalyticsService
from services.assistant_service import AIAttendanceAssistant
from services.notification_service import NotificationService
from services.export_service import ExportService

# Initialize storage and relational database schema
Config.initialize_directories()
Database.init_schema()

# Initialize AI Pipeline
detector = FaceDetector()
embedder = FaceEmbedder()
liveness_detector = LivenessDetector()
matcher = FaceMatcher()


def decode_base64_image(base64_str: str) -> Optional[np.ndarray]:
    """Decodes a base64 Data URL string to a BGR OpenCV numpy image."""
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        img_bytes = base64.b64decode(base64_str)
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        return cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"Base64 image decode error: {e}")
        return None


def get_all_enrolled_templates() -> list:
    """Fetches and decrypts all student biometric templates from database."""
    conn = Database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bt.student_id, bt.encrypted_embedding, s.full_name, c.name as class_name
        FROM biometric_templates bt
        JOIN students s ON bt.student_id = s.student_id
        LEFT JOIN classes c ON s.class_id = c.id
    """)
    rows = cursor.fetchall()
    conn.close()

    templates = []
    for r in rows:
        decrypted_vector = SecurityService.decrypt_biometric_vector(r["encrypted_embedding"])
        if decrypted_vector:
            templates.append({
                "student_id": r["student_id"],
                "name": r["full_name"],
                "class_name": r["class_name"] or "General",
                "embedding": decrypted_vector
            })
    return templates


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # -------------------------------------------------------------
    # 1. WEB UI ROUTES
    # -------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/kiosk", methods=["GET"])
    def kiosk_view():
        """Dedicated Fullscreen Autonomous Attendance Kiosk Mode."""
        return render_template("kiosk.html")

    # -------------------------------------------------------------
    # 2. AUTHENTICATION & RBAC APIS
    # -------------------------------------------------------------
    @app.route("/api/auth/login", methods=["POST"])
    def login():
        data = request.get_json() or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", "")).strip()

        if not email or not password:
            return jsonify({"status": "error", "message": "Email and password are required"}), 400

        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user or not SecurityService.verify_password(password, user["password_hash"]):
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        token_payload = {
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user["full_name"]
        }
        token = SecurityService.create_jwt_token(token_payload)

        # Log audit event
        conn = Database.get_connection()
        conn.execute("""
            INSERT INTO audit_logs (user_id, user_name, action, resource_type, resource_id, ip_address)
            VALUES (?, ?, 'LOGIN', 'users', ?, ?)
        """, (user["id"], user["full_name"], str(user["id"]), request.remote_addr))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["full_name"],
                "role": user["role"]
            }
        })

    @app.route("/api/auth/me", methods=["GET"])
    def get_profile():
        user = get_current_user() or {
            "user_id": 1,
            "email": "admin@institution.edu",
            "name": "System Administrator",
            "role": "ADMIN"
        }
        return jsonify({"status": "success", "user": user})

    # -------------------------------------------------------------
    # 3. DASHBOARD & ANALYTICS APIS
    # -------------------------------------------------------------
    @app.route("/api/stats/overview", methods=["GET"])
    def get_stats_overview():
        summary = AnalyticsService.get_dashboard_summary()
        return jsonify({"status": "success", "data": summary})

    @app.route("/api/analytics/trends", methods=["GET"])
    def get_attendance_trends():
        days = int(request.args.get("days", 7))
        trends = AnalyticsService.get_attendance_trends(days)
        return jsonify({"status": "success", "data": trends})

    @app.route("/api/analytics/low_attendance", methods=["GET"])
    def get_low_attendance():
        threshold = float(request.args.get("threshold", Config.LOW_ATTENDANCE_THRESHOLD_PERCENT))
        students = AnalyticsService.get_students_below_threshold(threshold)
        return jsonify({"status": "success", "threshold": threshold, "students": students})

    # -------------------------------------------------------------
    # 4. AI LIVE KIOSK RECOGNITION & LIVENESS API
    # -------------------------------------------------------------
    @app.route("/api/ai/recognize_frame", methods=["POST"])
    def recognize_frame():
        data = request.get_json() or {}
        frame_base64 = data.get("frame", "")
        kiosk_id = int(data.get("kiosk_id", 1))

        if not frame_base64:
            return jsonify({"status": "error", "message": "Frame data required"}), 400

        img = decode_base64_image(frame_base64)
        if img is None:
            return jsonify({"status": "error", "message": "Invalid frame"}), 400

        # Step 1: Detect all faces in frame
        detected_faces = detector.detect_faces(img)
        enrolled_templates = get_all_enrolled_templates()

        if not detected_faces:
            return jsonify({
                "status": "idle",
                "faces_count": 0,
                "faces": []
            })

        results = []
        for face_item in detected_faces:
            x, y, w, h = face_item["box"]
            face_gray = face_item["face_gray"]
            face_bgr = face_item["face_bgr"]

            # Step 2: Multi-metric Liveness & Anti-Spoofing check
            liveness_res = liveness_detector.check_liveness(face_bgr, face_gray)
            is_live = liveness_res["is_live"]
            liveness_score = liveness_res["confidence"]

            # Step 3: Biometric Vector Extraction & Matching
            embedding = embedder.extract_embedding(face_gray)
            is_matched, best_match, confidence = matcher.find_best_match(embedding, enrolled_templates)

            if not is_matched:
                AttendanceEngine.log_recognition_event(None, kiosk_id, confidence, liveness_score, "UNKNOWN")
                results.append({
                    "x": x, "y": y, "w": w, "h": h,
                    "is_matched": False,
                    "student_name": "Unknown Person",
                    "student_id": "",
                    "confidence": confidence,
                    "liveness": {"is_live": is_live, "confidence": liveness_score, "reason": liveness_res["reason"]},
                    "attendance": {"marked": False, "status": "UNKNOWN", "message": "Recognition Failed — Attendance Not Marked"}
                })
                continue

            student_id = best_match["student_id"]
            recognized_student = best_match["name"]
            student_class = best_match["class_name"]

            # Step 4: Automatic Kiosk Attendance Evaluation
            mark_res = AttendanceEngine.mark_attendance(
                student_id=student_id,
                confidence=confidence,
                liveness_verified=is_live,
                liveness_score=liveness_score,
                kiosk_id=kiosk_id
            )

            results.append({
                "x": x, "y": y, "w": w, "h": h,
                "is_matched": True,
                "student_id": student_id,
                "student_name": recognized_student,
                "class_name": student_class,
                "confidence": confidence,
                "liveness": {
                    "is_live": is_live,
                    "confidence": liveness_score,
                    "reason": liveness_res["reason"]
                },
                "attendance": mark_res
            })

        return jsonify({
            "status": "success",
            "faces_count": len(results),
            "faces": results
        })

    # -------------------------------------------------------------
    # 5. STUDENT REGISTRATION + BIOMETRIC DUPLICATE PREVENTION
    # -------------------------------------------------------------
    @app.route("/api/ai/register_sample", methods=["POST"])
    def register_sample():
        """
        Enrolls student face sample with strict single-face check, quality evaluation,
        liveness verification, and biometric duplicate face conflict check.
        """
        data = request.get_json() or {}
        student_id = str(data.get("student_id", "")).strip()
        student_name = str(data.get("full_name", data.get("student_name", ""))).strip()
        angle_type = str(data.get("angle_type", "FRONTAL")).upper()
        sample_num = int(data.get("sample_num", 1))
        frame_base64 = data.get("frame", "")

        if not student_id or not student_name or not frame_base64:
            return jsonify({"status": "error", "message": "Missing required fields (student_id, full_name, frame)"}), 400

        img = decode_base64_image(frame_base64)
        if img is None:
            return jsonify({"status": "error", "message": "Invalid image payload"}), 400

        # 1. Single Face Requirement
        detected = detector.detect_faces(img)
        if len(detected) == 0:
            return jsonify({
                "status": "error",
                "code": "NO_FACE_DETECTED",
                "message": "No face detected in frame. Please look directly at the registration camera."
            }), 400
        
        if len(detected) > 1:
            return jsonify({
                "status": "error",
                "code": "MULTIPLE_FACES_DETECTED",
                "message": f"Multiple faces detected ({len(detected)} faces found). Exactly ONE person must be in view during biometric registration."
            }), 400

        best_face = detected[0]
        quality = best_face["quality_score"]

        # 2. Image Quality Check
        if not quality["is_valid"]:
            return jsonify({
                "status": "error",
                "code": "QUALITY_CHECK_FAILED",
                "message": f"Image quality check failed: {quality['reason']}. Please ensure good frontal lighting without glare.",
                "quality": quality
            }), 400

        # 3. Liveness Check on Registration
        liveness_check = liveness_detector.check_liveness(best_face["face_bgr"], best_face["face_gray"])
        if not liveness_check["is_live"]:
            return jsonify({
                "status": "error",
                "code": "LIVENESS_FAILED",
                "message": "Liveness Verification Failed: Live human subject required for registration. Photo/screen spoofing rejected."
            }), 400

        # 4. Biometric Duplicate Face Check (Compare against all enrolled students)
        sample_embedding = embedder.extract_embedding(best_face["face_gray"])
        enrolled_templates = get_all_enrolled_templates()

        is_duplicate, conflicting_student, sim_pct = matcher.check_duplicate_face(
            new_embedding=sample_embedding,
            registered_templates=enrolled_templates,
            current_student_id=student_id
        )

        if is_duplicate and conflicting_student:
            return jsonify({
                "status": "duplicate_face_detected",
                "code": "DUPLICATE_FACE_CONFLICT",
                "message": f"⚠ DUPLICATE FACE DETECTED: This face appears to already be registered to student: {conflicting_student['name']} (Student ID: {conflicting_student['student_id']}) with {sim_pct}% biometric similarity. Registration rejected.",
                "conflicting_student": {
                    "name": conflicting_student["name"],
                    "student_id": conflicting_student["student_id"],
                    "similarity": sim_pct
                }
            }), 409

        # 5. Save Sample Crop to TrainingImage/
        filename = f"{student_name}.{student_id}.{angle_type}.{sample_num}.jpg"
        save_path = os.path.join(Config.TRAINING_IMG_DIR, filename)
        cv2.imwrite(save_path, best_face["face_gray"])

        return jsonify({
            "status": "success",
            "face_detected": True,
            "quality_passed": True,
            "quality_score": quality["score"],
            "angle_type": angle_type,
            "sample_num": sample_num,
            "message": f"Sample #{sample_num} ({angle_type}) successfully captured & validated."
        })

    @app.route("/api/ai/train_biometrics", methods=["POST"])
    def train_biometrics():
        data = request.get_json() or {}
        target_student_id = str(data.get("student_id", "")).strip()

        image_files = [f for f in os.listdir(Config.TRAINING_IMG_DIR) if f.endswith((".jpg", ".png"))]
        if not image_files:
            return jsonify({"status": "error", "message": "No face samples found in dataset"}), 400

        student_crops: Dict[str, list] = {}
        for fname in image_files:
            parts = fname.split(".")
            if len(parts) >= 4:
                sid = parts[1]
                if target_student_id and sid != target_student_id:
                    continue
                img_path = os.path.join(Config.TRAINING_IMG_DIR, fname)
                crop_gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if crop_gray is not None:
                    if sid not in student_crops:
                        student_crops[sid] = []
                    student_crops[sid].append(crop_gray)

        if not student_crops:
            return jsonify({"status": "error", "message": "No valid sample crops found for student"}), 400

        conn = Database.get_connection()
        cursor = conn.cursor()
        enrolled_count = 0

        enrolled_templates = get_all_enrolled_templates()

        for sid, crops in student_crops.items():
            master_vector = embedder.extract_multi_angle_average(crops)
            if master_vector:
                # Final duplicate check on master template
                is_duplicate, conflicting, sim_pct = matcher.check_duplicate_face(
                    new_embedding=master_vector,
                    registered_templates=enrolled_templates,
                    current_student_id=sid
                )
                if is_duplicate and conflicting:
                    conn.close()
                    return jsonify({
                        "status": "duplicate_face_detected",
                        "message": f"⚠ Biometric enrollment aborted: Face matches existing student {conflicting['name']} ({conflicting['student_id']}) with {sim_pct}% similarity."
                    }), 409

                encrypted_blob = SecurityService.encrypt_biometric_vector(master_vector)
                cursor.execute("""
                    INSERT INTO biometric_templates 
                    (student_id, encrypted_embedding, embedding_dim, sample_count, quality_score, algorithm_version)
                    VALUES (?, ?, 128, ?, 96.5, 'v2.0-multi-angle')
                    ON CONFLICT(student_id) DO UPDATE SET
                        encrypted_embedding = excluded.encrypted_embedding,
                        sample_count = excluded.sample_count,
                        updated_at = CURRENT_TIMESTAMP
                """, (sid, encrypted_blob, len(crops)))
                enrolled_count += 1

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Biometric master templates securely generated and encrypted with AES-256 for {enrolled_count} student(s)!",
            "enrolled_students": enrolled_count
        })

    # -------------------------------------------------------------
    # 6. SESSIONS & TIMETABLE APIS
    # -------------------------------------------------------------
    @app.route("/api/sessions", methods=["GET"])
    def get_sessions():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, c.name as class_name, t.full_name as teacher_name
            FROM attendance_sessions s
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN teachers t ON s.teacher_id = t.id
            ORDER BY s.id DESC LIMIT 20
        """)
        sessions = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "sessions": sessions})

    @app.route("/api/sessions/start", methods=["POST"])
    def start_session():
        data = request.get_json() or {}
        class_id = data.get("class_id", 1)
        subject_name = data.get("subject_name", "General Lecture")
        room_number = data.get("room_number", "Room 101")
        grace_mins = int(data.get("grace_period_mins", Config.DEFAULT_GRACE_PERIOD_MINS))
        late_mins = int(data.get("late_cutoff_mins", Config.DEFAULT_LATE_CUTOFF_MINS))

        now = datetime.datetime.now()
        start_str = now.strftime("%H:%M")
        end_str = (now + datetime.timedelta(hours=1)).strftime("%H:%M")

        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO attendance_sessions
            (class_id, teacher_id, subject_name, room_number, scheduled_start, scheduled_end, grace_period_mins, late_cutoff_mins, status)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, 'ACTIVE')
        """, (class_id, subject_name, room_number, start_str, end_str, grace_mins, late_mins))

        session_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Session '{subject_name}' started in {room_number}!",
            "session_id": session_id
        })

    @app.route("/api/sessions/<int:session_id>/end", methods=["POST"])
    def end_session(session_id: int):
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE attendance_sessions SET status = 'COMPLETED' WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Session #{session_id} ended."})

    # -------------------------------------------------------------
    # 7. ATTENDANCE RECORDS & AUDITED MANUAL OVERRIDE
    # -------------------------------------------------------------
    @app.route("/api/attendance/records", methods=["GET"])
    def get_attendance_records():
        date_param = request.args.get("date")
        if date_param:
            if "-" in date_param and len(date_param.split("-")[0]) == 4:  # YYYY-MM-DD
                p = date_param.split("-")
                date_filter = f"{p[2]}-{p[1]}-{p[0]}"
            else:
                date_filter = date_param
        else:
            date_filter = datetime.datetime.now().strftime("%d-%m-%Y")

        class_id = request.args.get("class_id", type=int)
        records = ExportService.get_complete_attendance_data(date_filter, class_id)
        return jsonify({"status": "success", "date": date_filter, "records": records})

    @app.route("/api/attendance/override", methods=["POST"])
    def override_attendance():
        data = request.get_json() or {}
        record_id = int(data.get("record_id", 0))
        student_id = str(data.get("student_id", "")).strip()
        date_str = str(data.get("date", datetime.datetime.now().strftime("%d-%m-%Y"))).strip()
        new_status = str(data.get("new_status", "")).upper()
        reason = str(data.get("reason", "")).strip()

        user = get_current_user() or {"user_id": 1, "name": "System Administrator"}

        # If record_id is 0 but student_id is provided, create new override record
        if record_id <= 0 and student_id:
            conn = Database.get_connection()
            cursor = conn.cursor()
            time_str = datetime.datetime.now().strftime("%H:%M:%S")
            cursor.execute("""
                INSERT INTO attendance_records (student_id, date, time, status, confidence, liveness_verified, is_manual_override, override_reason, override_by_user_id)
                VALUES (?, ?, ?, ?, 100.0, 1, 1, ?, ?)
                ON CONFLICT(student_id, session_id, date) DO UPDATE SET
                    status = excluded.status,
                    is_manual_override = 1,
                    override_reason = excluded.override_reason,
                    override_by_user_id = excluded.override_by_user_id
            """, (student_id, date_str, time_str, new_status, reason, user.get("user_id", 1)))
            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Log audit
            Database.log_audit(
                user_id=user.get("user_id", 1),
                action="MANUAL_ATTENDANCE_CREATED",
                entity="attendance_records",
                entity_id=record_id,
                old_value="ABSENT",
                new_value=new_status,
                reason=reason,
                ip_address=request.remote_addr or "127.0.0.1"
            )
            return jsonify({"status": "success", "message": f"Attendance for {student_id} set to {new_status} (audited)."})

        res = AttendanceEngine.manual_override_attendance(
            record_id=record_id,
            new_status=new_status,
            reason=reason,
            user_id=user.get("user_id", 1),
            user_name=user.get("name", "Administrator"),
            ip_address=request.remote_addr or "127.0.0.1"
        )
        return jsonify(res)

    @app.route("/api/recognition_events", methods=["GET"])
    def get_recognition_events():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT re.*, s.full_name as student_name, k.name as kiosk_name
            FROM recognition_events re
            LEFT JOIN students s ON re.student_id = s.student_id
            LEFT JOIN kiosks k ON re.kiosk_id = k.id
            ORDER BY re.id DESC LIMIT 40
        """)
        events = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "events": events})

    # -------------------------------------------------------------
    # 8. KIOSKS, STUDENTS, SETTINGS, AUDIT APIS
    # -------------------------------------------------------------
    @app.route("/api/kiosks", methods=["GET"])
    def get_kiosks():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM kiosks ORDER BY id ASC")
        kiosks = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "kiosks": kiosks})

    @app.route("/api/students", methods=["GET", "POST"])
    def handle_students():
        conn = Database.get_connection()
        cursor = conn.cursor()

        if request.method == "POST":
            data = request.get_json() or {}
            sid = str(data.get("student_id", "")).strip()
            name = str(data.get("full_name", "")).strip()
            dept_id = data.get("department_id", 1)
            class_id = data.get("class_id", 1)
            pemail = data.get("parent_email", "")
            pphone = data.get("parent_phone", "")

            if not sid or not name:
                conn.close()
                return jsonify({"status": "error", "message": "Student ID and Full Name are required"}), 400

            cursor.execute("""
                INSERT INTO students (student_id, full_name, department_id, class_id, parent_email, parent_phone, enrollment_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    department_id = excluded.department_id,
                    class_id = excluded.class_id,
                    parent_email = excluded.parent_email,
                    parent_phone = excluded.parent_phone
            """, (sid, name, dept_id, class_id, pemail, pphone, datetime.datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": f"Student {name} ({sid}) registered successfully!"})

        cursor.execute("""
            SELECT s.*, c.name as class_name, d.name as department_name,
                   (CASE WHEN bt.id IS NOT NULL THEN 1 ELSE 0 END) as has_biometrics,
                   ROUND((COUNT(ar.id) * 100.0 / MAX(1, (SELECT COUNT(DISTINCT date) FROM attendance_records))), 1) as attendance_percentage
            FROM students s
            LEFT JOIN classes c ON s.class_id = c.id
            LEFT JOIN departments d ON s.department_id = d.id
            LEFT JOIN biometric_templates bt ON s.student_id = bt.student_id
            LEFT JOIN attendance_records ar ON s.student_id = ar.student_id AND ar.status IN ('PRESENT', 'LATE')
            GROUP BY s.id
            ORDER BY s.id DESC
        """)
        students = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "students": students})

    @app.route("/api/settings", methods=["GET", "POST"])
    def handle_settings():
        conn = Database.get_connection()
        cursor = conn.cursor()

        if request.method == "POST":
            data = request.get_json() or {}
            for k, v in data.items():
                cursor.execute("""
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """, (k, str(v)))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": "Attendance settings updated successfully."})

        cursor.execute("SELECT key, value FROM system_settings")
        settings_map = {r["key"]: r["value"] for r in cursor.fetchall()}
        conn.close()

        # Defaults if not present in DB
        defaults = {
            "start_time": "09:00",
            "grace_period_mins": str(Config.DEFAULT_GRACE_PERIOD_MINS),
            "late_cutoff_mins": str(Config.DEFAULT_LATE_CUTOFF_MINS),
            "duplicate_cooldown_secs": str(Config.DUPLICATE_RECOGNITION_COOLDOWN_SECS),
            "confidence_threshold": str(Config.MIN_KIOSK_CONFIDENCE_THRESHOLD),
            "auto_mark": "1",
            "liveness_enabled": "1",
            "manual_fallback_enabled": "1"
        }
        defaults.update(settings_map)
        return jsonify({"status": "success", "settings": defaults})

    @app.route("/api/cameras", methods=["GET"])
    def get_cameras():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cameras ORDER BY id ASC")
        cameras = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "cameras": cameras})

    @app.route("/api/audit/logs", methods=["GET"])
    def get_audit_logs():
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
        logs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({"status": "success", "logs": logs})

    # -------------------------------------------------------------
    # 9. GROUNDED AI ASSISTANT, NOTIFICATIONS, EXPORT
    # -------------------------------------------------------------
    @app.route("/api/assistant/query", methods=["POST"])
    def assistant_query():
        data = request.get_json() or {}
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            return jsonify({"status": "error", "message": "Prompt is required"}), 400
        res = AIAttendanceAssistant.query(prompt)
        return jsonify(res)

    @app.route("/api/notifications", methods=["GET"])
    def get_notifications():
        user = get_current_user() or {"user_id": 1}
        notifs = NotificationService.get_user_notifications(user.get("user_id", 1))
        return jsonify({"status": "success", "notifications": notifs})

    @app.route("/api/reports/export/excel", methods=["GET"])
    @app.route("/api/reports/export/xlsx", methods=["GET"])
    def export_excel_report():
        date_param = request.args.get("date")
        if date_param and "-" in date_param and len(date_param.split("-")[0]) == 4:
            p = date_param.split("-")
            date_filter = f"{p[2]}-{p[1]}-{p[0]}"
        else:
            date_filter = date_param or datetime.datetime.now().strftime("%d-%m-%Y")

        class_id = request.args.get("class_id", type=int)
        class_prefix = f"Class{class_id}_" if class_id else ""
        excel_bytes = ExportService.generate_attendance_excel(date_filter, class_id)
        filename = f"Attendance_{class_prefix}{date_filter}.xlsx"

        return Response(
            excel_bytes,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )

    @app.route("/api/reports/export/csv", methods=["GET"])
    def export_csv_report():
        date_param = request.args.get("date")
        if date_param and "-" in date_param and len(date_param.split("-")[0]) == 4:
            p = date_param.split("-")
            date_filter = f"{p[2]}-{p[1]}-{p[0]}"
        else:
            date_filter = date_param or datetime.datetime.now().strftime("%d-%m-%Y")

        csv_text = ExportService.generate_attendance_csv(date_filter)
        filename = f"Attendance_Audit_Report_{date_filter}.csv"

        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={filename}"}
        )

    @app.route("/api/offline/sync", methods=["POST"])
    def sync_offline_queue():
        res = OfflineSyncEngine.process_sync_queue()
        return jsonify(res)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print("=" * 75)
    print("  VISIONATTEND AI - PRODUCTION FACIAL RECOGNITION PLATFORM")
    print(f"  Live Kiosk & Dashboard running at: http://127.0.0.1:{port}")
    print("=" * 75)
    app.run(host="0.0.0.0", port=port, debug=False)
