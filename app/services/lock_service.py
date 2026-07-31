from datetime import datetime, time
from app.models import db
from app.models.live_class import LiveClass, AuditLog

def check_and_auto_lock_classes():
    """
    Checks all live classes and auto-locks classes whose class_date has passed 11:59 PM.
    """
    now = datetime.now()
    unlocked_classes = LiveClass.query.filter_by(is_locked=False).all()
    
    locked_count = 0
    for cls in unlocked_classes:
        # Class cutoff is 11:59:59 PM on class_date
        cutoff = datetime.combine(cls.class_date, time(23, 59, 59))
        if now > cutoff:
            cls.is_locked = True
            cls.locked_at = now
            
            # Log audit event
            log = AuditLog(
                entity_type='LiveClass',
                entity_id=cls.class_id,
                action='AUTO_LOCK',
                reason='Automatic lock triggered after 11:59 PM cut-off',
                performed_by='SYSTEM'
            )
            db.session.add(log)
            locked_count += 1

    if locked_count > 0:
        db.session.commit()
    return locked_count


def unlock_class(class_id, reason, admin_username='admin'):
    """
    Unlocks a locked live class with mandatory reason and writes an AuditLog entry.
    """
    cls = LiveClass.query.filter_by(class_id=class_id).first()
    if not cls:
        return False, "Class not found."

    if not reason or not reason.strip():
        return False, "Mandatory unlock reason must be provided."

    cls.is_locked = False
    cls.unlock_reason = reason.strip()

    audit_entry = AuditLog(
        entity_type='LiveClass',
        entity_id=cls.class_id,
        action='UNLOCK',
        reason=reason.strip(),
        performed_by=admin_username
    )
    db.session.add(audit_entry)
    db.session.commit()
    return True, f"Class {cls.class_id} unlocked successfully."
