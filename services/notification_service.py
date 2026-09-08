import datetime
from typing import List, Dict, Any, Optional
from core.database import Database

class NotificationService:
    """Notification & Alert Management Service."""

    @staticmethod
    def create_notification(recipient_id: int, title: str, message: str, notif_type: str = "SYSTEM") -> Dict[str, Any]:
        """Creates and stores an in-app notification for a user."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO notifications (recipient_id, title, message, type, is_read)
            VALUES (?, ?, ?, ?, 0)
        """, (recipient_id, title, message, notif_type))

        notif_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "id": notif_id,
            "title": title,
            "message": message,
            "type": notif_type,
            "is_read": False,
            "created_at": datetime.datetime.now().isoformat()
        }

    @staticmethod
    def get_user_notifications(recipient_id: int, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Fetches notifications for the given user."""
        conn = Database.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM notifications WHERE recipient_id = ?"
        params = [recipient_id]

        if unread_only:
            query += " AND is_read = 0"
        query += " ORDER BY id DESC LIMIT 50"

        cursor.execute(query, params)
        notifications = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return notifications

    @staticmethod
    def mark_as_read(notif_id: int) -> bool:
        """Marks a notification as read."""
        conn = Database.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
        conn.commit()
        conn.close()
        return True
