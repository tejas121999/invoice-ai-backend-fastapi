from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    entity: str,
    entity_id: int,
    action: str,
    performed_by: int,
    old_data: dict,
    new_data: dict
):
    audit = AuditLog(
        entity=entity,
        entityId=entity_id,
        action=action,
        performedBy=performed_by,
        oldData=old_data,
        newData=new_data
    )
    db.add(audit)
