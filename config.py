import os
import hashlib

class Config:
    """Production configuration and environment constants."""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Core Security
    SECRET_KEY = os.getenv("SECRET_KEY", "prod-ai-attendance-secret-key-super-secure-2026")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-attendance-auth-token-secret-key-9988")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRATION_HOURS = 24
    
    # Biometric Encryption (AES-256 Key derived from secret)
    BIOMETRIC_ENCRYPTION_KEY = hashlib.sha256(
        os.getenv("BIOMETRIC_MASTER_KEY", "biometric-aes-256-master-key-secure").encode("utf-8")
    ).digest()
    
    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL", 
        f"sqlite:///{os.path.join(BASE_DIR, 'attendance_enterprise.db')}"
    )
    
    # AI Engine & Biometric Thresholds
    HAAR_CASCADE_PATH = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
    FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.62"))  # Cosine similarity for recognition
    MIN_KIOSK_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_KIOSK_CONFIDENCE_THRESHOLD", "85.0"))  # 85% min confidence for auto-mark
    DUPLICATE_FACE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_FACE_SIMILARITY_THRESHOLD", "0.78"))  # 78%+ cosine sim = duplicate person
    LIVENESS_BLUR_THRESHOLD = float(os.getenv("LIVENESS_BLUR_THRESHOLD", "85.0"))  # Laplacian variance threshold
    MIN_FACE_SIZE = (80, 80)
    EMBEDDING_DIM = 128
    
    # Attendance Engine Defaults
    DEFAULT_GRACE_PERIOD_MINS = 10
    DEFAULT_LATE_CUTOFF_MINS = 30
    DEFAULT_MIN_PRESENCE_MINS = 45
    DUPLICATE_RECOGNITION_COOLDOWN_SECS = 300  # 5 minutes cooldown for duplicate recognition
    LOW_ATTENDANCE_THRESHOLD_PERCENT = 75.0
    
    # File Storage Paths
    STUDENT_DETAILS_DIR = os.path.join(BASE_DIR, "StudentDetails")
    TRAINING_IMG_DIR = os.path.join(BASE_DIR, "TrainingImage")
    TRAINING_LABEL_DIR = os.path.join(BASE_DIR, "TrainingImageLabel")
    ATTENDANCE_DIR = os.path.join(BASE_DIR, "Attendance")
    REPORTS_DIR = os.path.join(BASE_DIR, "Reports")
    AUDIT_DIR = os.path.join(BASE_DIR, "AuditLogs")

    @classmethod
    def initialize_directories(cls):
        """Ensure all required physical storage directories exist."""
        for path in [
            cls.STUDENT_DETAILS_DIR,
            cls.TRAINING_IMG_DIR,
            cls.TRAINING_LABEL_DIR,
            cls.ATTENDANCE_DIR,
            cls.REPORTS_DIR,
            cls.AUDIT_DIR
        ]:
            os.makedirs(path, exist_ok=True)
