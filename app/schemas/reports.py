from pydantic import BaseModel


class RevenueRow(BaseModel):
    plan_id: int
    plan_name: str
    charges: int
    revenue: float


class RevenueReport(BaseModel):
    rows: list[RevenueRow]
    total_charges: int
    total_revenue: float


class TicketReport(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_category: dict[str, int]
    avg_resolution_hours: float | None


class SlaReport(BaseModel):
    tracked: int
    response_breached: int
    resolution_breached: int
    compliance_percent: float


class OutageReport(BaseModel):
    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    avg_duration_hours: float | None


class UsageReport(BaseModel):
    records: int
    totals: dict[str, int]
