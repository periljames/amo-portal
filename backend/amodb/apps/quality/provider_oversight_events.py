"""Immutable projections of authorized Quality provider status changes."""
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session

def record_status_snapshot(db: Session, *, amo_id: str, supplier_id: int, actor_id: str,
                           previous_status: str | None, current_status: str,
                           action: str, source_reference: str | None = None) -> None:
    db.execute(text("""INSERT INTO external_provider_oversight_snapshots
      (id,amo_id,supplier_id,actor_user_id,previous_status,current_status,
       risk_level,action,source_reference)
      SELECT :id,s.amo_id,s.id,:actor,:previous,:current,CAST(s.risk_level AS TEXT),
             :action,:source FROM procurement_suppliers s
      WHERE s.amo_id=:amo AND s.id=:supplier"""),
      {"id":str(uuid4()),"amo":amo_id,"supplier":supplier_id,"actor":actor_id,
       "previous":previous_status,"current":current_status,
       "action":action,"source":source_reference})
