from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now (MySQL DATETIME columns are naive), so comparisons work everywhere."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
