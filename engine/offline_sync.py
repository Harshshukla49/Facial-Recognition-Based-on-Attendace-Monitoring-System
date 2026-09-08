import json
import os
import datetime
from typing import List, Dict, Any
from config import Config
from engine.attendance_engine import AttendanceEngine

class OfflineSyncEngine:
    """
    Offline Edge Attendance Queue.
    Stores events locally during connectivity loss and synchronizes automatically upon reconnect.
    """
    
    QUEUE_FILE = os.path.join(Config.BASE_DIR, "offline_attendance_queue.json")

    @classmethod
    def enqueue_offline_event(cls, student_id: str, confidence: float, timestamp: str, camera_id: int = 1):
        """Appends an event to the local persistent offline queue."""
        queue = cls.get_queued_events()
        event = {
            "student_id": student_id,
            "confidence": confidence,
            "timestamp": timestamp,
            "camera_id": camera_id,
            "queued_at": datetime.datetime.now().isoformat()
        }
        queue.append(event)
        with open(cls.QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)

    @classmethod
    def get_queued_events(cls) -> List[Dict[str, Any]]:
        """Reads currently pending offline events."""
        if not os.path.isfile(cls.QUEUE_FILE):
            return []
        try:
            with open(cls.QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def process_sync_queue(cls) -> Dict[str, Any]:
        """Processes and syncs all pending offline events into the primary database."""
        queue = cls.get_queued_events()
        if not queue:
            return {"status": "success", "synced_count": 0, "message": "Queue is empty"}

        synced_count = 0
        errors = []

        for item in queue:
            try:
                res = AttendanceEngine.mark_attendance(
                    student_id=item["student_id"],
                    confidence=item.get("confidence", 95.0),
                    liveness_verified=True,
                    camera_id=item.get("camera_id")
                )
                if res.get("status") in ["success", "already_marked"]:
                    synced_count += 1
            except Exception as e:
                errors.append(f"Failed sync for {item.get('student_id')}: {str(e)}")

        # Clear queue after processing
        if os.path.isfile(cls.QUEUE_FILE):
            os.remove(cls.QUEUE_FILE)

        return {
            "status": "success",
            "synced_count": synced_count,
            "total_items": len(queue),
            "errors": errors,
            "message": f"Successfully synchronized {synced_count} offline records."
        }
