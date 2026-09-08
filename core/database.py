import sqlite3
import os
import json
import datetime
import time
from typing import List, Dict, Any, Optional
from config import Config
from core.security import SecurityService

class Database:
    """Enterprise relational database manager with connection pooling, migrations, and duplicate constraints."""
    
    @staticmethod
    def get_connection() -> sqlite3.Connection:
        Config.initialize_directories()
        db_path = Config.DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path, timeout=25.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @classmethod
    def init_schema(cls):
        """Initializes relational tables, indexes, and constraints."""
        conn = cls.get_connection()
        cursor = conn.cursor()

        # 1. Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN', 'TEACHER', 'STUDENT', 'PARENT')),
            full_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 2. Departments table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL
        )
        """)

        # 3. Classes table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            semester INTEGER NOT NULL DEFAULT 1,
            academic_year TEXT NOT NULL,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE CASCADE
        )
        """)

        # 4. Students table (Unique on student_id)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            student_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department_id INTEGER,
            class_id INTEGER,
            parent_email TEXT,
            parent_phone TEXT,
            enrollment_date TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
            FOREIGN KEY (class_id) REFERENCES classes (id) ON DELETE SET NULL
        )
        """)

        # 5. Teachers table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            employee_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            department_id INTEGER,
            designation TEXT DEFAULT 'Professor',
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL
        )
        """)

        # 6. Biometric Templates table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS biometric_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            encrypted_embedding TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL DEFAULT 128,
            sample_count INTEGER NOT NULL DEFAULT 48,
            quality_score REAL NOT NULL DEFAULT 96.0,
            algorithm_version TEXT NOT NULL DEFAULT 'v2.0-multi-angle',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (student_id) ON DELETE CASCADE
        )
        """)

        # 7. Attendance Sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER,
            teacher_id INTEGER,
            subject_name TEXT NOT NULL,
            room_number TEXT NOT NULL,
            scheduled_start TEXT NOT NULL,
            scheduled_end TEXT NOT NULL,
            grace_period_mins INTEGER NOT NULL DEFAULT 10,
            late_cutoff_mins INTEGER NOT NULL DEFAULT 30,
            min_duration_mins INTEGER NOT NULL DEFAULT 45,
            status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'PAUSED', 'COMPLETED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes (id) ON DELETE SET NULL,
            FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE SET NULL
        )
        """)

        # 8. Kiosks table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kiosks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ONLINE' CHECK(status IN ('ONLINE', 'OFFLINE')),
            ip_address TEXT,
            last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 9. Attendance Records table (Enforced Unique Constraint: 1 student + 1 session + 1 date = 1 record)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PRESENT', 'LATE', 'ABSENT', 'HALF_DAY', 'EXCUSED')),
            confidence REAL NOT NULL DEFAULT 98.0,
            liveness_verified INTEGER NOT NULL DEFAULT 1,
            kiosk_id INTEGER DEFAULT 1,
            is_manual_override INTEGER NOT NULL DEFAULT 0,
            override_reason TEXT,
            override_by_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES attendance_sessions (id) ON DELETE SET NULL,
            FOREIGN KEY (student_id) REFERENCES students (student_id) ON DELETE CASCADE,
            FOREIGN KEY (kiosk_id) REFERENCES kiosks (id) ON DELETE SET NULL,
            UNIQUE(student_id, session_id, date)
        )
        """)

        # 10. Recognition Events table (Captures EVERY camera face detection event for auditing)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recognition_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            kiosk_id INTEGER DEFAULT 1,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confidence REAL NOT NULL,
            liveness_score REAL NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('MATCH_SUCCESS', 'ALREADY_MARKED', 'LOW_CONFIDENCE', 'SPOOF_REJECTED', 'UNKNOWN')),
            event_type TEXT NOT NULL DEFAULT 'KIOSK_SCAN',
            FOREIGN KEY (student_id) REFERENCES students (student_id) ON DELETE SET NULL,
            FOREIGN KEY (kiosk_id) REFERENCES kiosks (id) ON DELETE SET NULL
        )
        """)

        # 11. Entry/Exit Logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS entry_exit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            camera_id INTEGER,
            event_type TEXT NOT NULL CHECK(event_type IN ('ENTRY', 'EXIT')),
            timestamp TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 95.0,
            FOREIGN KEY (student_id) REFERENCES students (student_id) ON DELETE CASCADE
        )
        """)

        # 12. Cameras table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            ip_stream_url TEXT,
            status TEXT NOT NULL DEFAULT 'ONLINE' CHECK(status IN ('ONLINE', 'OFFLINE')),
            last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 13. Notifications table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'SYSTEM',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recipient_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """)

        # 14. Audit Logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            old_value TEXT,
            new_value TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 15. System Settings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Performance & Uniqueness Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_student_id ON students(student_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_date ON attendance_records(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_student ON attendance_records(student_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recog_time ON recognition_events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_class ON attendance_sessions(class_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp)")

        conn.commit()
        conn.close()

        # Seed baseline data
        cls.seed_default_data()

    @classmethod
    def seed_default_data(cls):
        """Seeds initial departments, classes, demo accounts, default kiosks, and settings."""
        conn = cls.get_connection()
        cursor = conn.cursor()

        # Admin User
        admin_email = "admin@institution.edu"
        cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
        if not cursor.fetchone():
            hashed_pw = SecurityService.hash_password("admin123")
            cursor.execute("""
                INSERT INTO users (email, password_hash, role, full_name, is_active)
                VALUES (?, ?, 'ADMIN', 'System Administrator', 1)
            """, (admin_email, hashed_pw))

        # Teacher User & Profile
        teacher_email = "teacher@institution.edu"
        cursor.execute("SELECT id FROM users WHERE email = ?", (teacher_email,))
        user_row = cursor.fetchone()
        if not user_row:
            hashed_pw = SecurityService.hash_password("teacher123")
            cursor.execute("""
                INSERT INTO users (email, password_hash, role, full_name, is_active)
                VALUES (?, ?, 'TEACHER', 'Dr. Sarah Connor', 1)
            """, (teacher_email, hashed_pw))
            teacher_user_id = cursor.lastrowid
        else:
            teacher_user_id = user_row["id"]

        # Departments
        departments = [
            ("Computer Science & Engineering", "CSE"),
            ("Electronics & Communication", "ECE"),
            ("Information Technology", "IT"),
            ("Mechanical Engineering", "ME")
        ]
        for name, code in departments:
            cursor.execute("INSERT OR IGNORE INTO departments (name, code) VALUES (?, ?)", (name, code))

        # Teacher record in teachers table
        cursor.execute("SELECT id FROM teachers WHERE employee_id = 'EMP-101'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO teachers (user_id, employee_id, full_name, department_id, designation)
                VALUES (?, 'EMP-101', 'Dr. Sarah Connor', 1, 'Professor')
            """, (teacher_user_id,))

        # Classes
        cursor.execute("SELECT id, code FROM departments WHERE code = 'CSE'")
        cse_dept = cursor.fetchone()
        if cse_dept:
            classes = [
                (cse_dept["id"], "B.Tech CSE - 3rd Year (Sec A)", "CSE-3A", 5, "2025-2026"),
                (cse_dept["id"], "B.Tech CSE - 3rd Year (Sec B)", "CSE-3B", 5, "2025-2026"),
                (cse_dept["id"], "B.Tech CSE - 4th Year", "CSE-4A", 7, "2025-2026")
            ]
            for dept_id, cname, ccode, sem, yr in classes:
                cursor.execute("""
                    INSERT OR IGNORE INTO classes (department_id, name, code, semester, academic_year)
                    VALUES (?, ?, ?, ?, ?)
                """, (dept_id, cname, ccode, sem, yr))

        # Seed Baseline Students
        cursor.execute("SELECT COUNT(*) as count FROM students")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("SELECT id FROM classes WHERE code = 'CSE-3A'")
            class_row = cursor.fetchone()
            class_id = class_row["id"] if class_row else 1
            dept_id = cse_dept["id"] if cse_dept else 1

            initial_students = [
                ("51230249", "Harsh Shukla", "harsh.parent@example.com", "+91 9876543210"),
                ("51230250", "Rahul Sharma", "rahul.parent@example.com", "+91 9876543211"),
                ("51230251", "Priya Singh", "priya.parent@example.com", "+91 9876543212"),
                ("51230252", "Aman Verma", "aman.parent@example.com", "+91 9876543213"),
                ("51230253", "Sneha Patel", "sneha.parent@example.com", "+91 9876543214"),
                ("51230254", "Aditya Prajapati", "aditya.parent@example.com", "+91 9876543215")
            ]
            for sid, name, pemail, pphone in initial_students:
                cursor.execute("""
                    INSERT OR IGNORE INTO students (student_id, full_name, department_id, class_id, parent_email, parent_phone, enrollment_date)
                    VALUES (?, ?, ?, ?, ?, ?, '2023-08-01')
                """, (sid, name, dept_id, class_id, pemail, pphone))

        # Seed Kiosks
        kiosks = [
            ("Kiosk 01 - Main Entrance", "Campus Main Gate Kiosk", "ONLINE", "192.168.1.101"),
            ("Kiosk 02 - CSE Building", "CSE Department Hallway", "ONLINE", "192.168.1.102"),
            ("Kiosk 03 - Computer Lab", "Lab Complex 02", "ONLINE", "192.168.1.103")
        ]
        cursor.execute("SELECT COUNT(*) as count FROM kiosks")
        if cursor.fetchone()["count"] == 0:
            for kname, kloc, kst, kip in kiosks:
                cursor.execute("""
                    INSERT INTO kiosks (name, location, status, ip_address)
                    VALUES (?, ?, ?, ?)
                """, (kname, kloc, kst, kip))

        # Cameras
        cameras = [
            ("Main Gate Kiosk (Cam 01)", "Campus Main Gate Entrance", "rtsp://192.168.1.101/live", "ONLINE"),
            ("Classroom A Kiosk (Cam 02)", "Block B - Room 204", "rtsp://192.168.1.102/live", "ONLINE"),
            ("AI & Robotics Lab (Cam 03)", "Lab Building - Room 102", "rtsp://192.168.1.103/live", "ONLINE"),
            ("Library Entrance (Cam 04)", "Central Library Gate", "rtsp://192.168.1.104/live", "OFFLINE")
        ]
        cursor.execute("SELECT COUNT(*) as count FROM cameras")
        if cursor.fetchone()["count"] == 0:
            for cname, loc, url, st in cameras:
                cursor.execute("""
                    INSERT INTO cameras (name, location, ip_stream_url, status)
                    VALUES (?, ?, ?, ?)
                """, (cname, loc, url, st))

        # Default Active Attendance Session
        cursor.execute("SELECT COUNT(*) as count FROM attendance_sessions WHERE status = 'ACTIVE'")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("SELECT id FROM classes LIMIT 1")
            c = cursor.fetchone()
            cid = c["id"] if c else 1
            now_time = datetime.datetime.now()
            start_str = now_time.strftime("%H:%M")
            end_str = (now_time + datetime.timedelta(hours=1)).strftime("%H:%M")
            cursor.execute("""
                INSERT INTO attendance_sessions 
                (class_id, teacher_id, subject_name, room_number, scheduled_start, scheduled_end, grace_period_mins, late_cutoff_mins, status)
                VALUES (?, 1, 'Artificial Intelligence & Neural Networks', 'Lab 02', ?, ?, 10, 30, 'ACTIVE')
            """, (cid, start_str, end_str))

        conn.commit()
        conn.close()
