def apply_search(query, model, value: str | None, fields: tuple[str, ...]):
    if not value:
        return query
    from sqlalchemy import or_
    return query.where(or_(*(getattr(model, field).ilike(f"%{value}%") for field in fields)))
