from fastapi import APIRouter
from app.api.v1 import auth, users, customers, plans
from app.api.v1 import addresses, sims, devices, subscriptions, usage
from app.api.v1 import towers, equipment, outages, technicians
from app.api.v1 import tickets, ticket_assignments, sla, service_requests
from app.api.v1 import notifications, dashboard, reports, audit_logs

api_router = APIRouter()
for module in (
    auth, users, customers, plans, addresses, sims, devices, subscriptions,
    usage, towers, equipment, outages, technicians, tickets,
    ticket_assignments, sla, service_requests, notifications,
    dashboard, reports, audit_logs,
):
    api_router.include_router(module.router)
