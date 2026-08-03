from sqlalchemy.orm import Session
from app.repositories.audit_repository import create_audit_log


def save_audit_log(
    db: Session,
    entity: str,
    entity_id: int,
    action: str,
    user_id: int | None,
    old_data: dict,
    new_data: dict
):

    create_audit_log(
        db=db,
        entity=entity,
        entity_id=entity_id,
        action=action,
        performed_by=user_id,
        old_data=old_data,
        new_data=new_data
    )
