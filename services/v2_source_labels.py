"""Present authorized filenames without replacing original citation identities."""
import json
from uuid import UUID
from services.tenant_context import current_owner
from services.database import get_connection

POLICY='v2-authorized-source-filenames/1'

def label_owned_sources(bundle):
    owner=current_owner()
    if not owner:return bundle
    ids=[]
    for source in bundle['sources']:
        try:ids.append(str(UUID(str(source['document_name']))))
        except (ValueError,TypeError,KeyError):continue
    if not ids:return bundle
    with get_connection() as c:
        rows=c.execute("SELECT id,filename FROM documents WHERE owner_id=%s AND id=ANY(%s::uuid[]) AND status='ready'",(owner,ids)).fetchall()
    names={str(row[0]):row[1] for row in rows}
    from services.evidence_trace import trace_event
    trace_event('owned_source_labels',metadata={'policy':POLICY,'document_ids':list(names)},raw={'source_labels':names})
    text=bundle['context_text']
    for source in bundle['sources']:
        did=source['document_name'];name=names.get(did)
        if name is not None:
            old=f"[{source['ref']}] Document: {did} | Page:"
            text=text.replace(old,f"[{source['ref']}] Document: {did} | Filename: {json.dumps(name,ensure_ascii=True)} | Page:",1)
    return {**bundle,'context_text':text}
