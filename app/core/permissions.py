from fastapi import HTTPException

ROLE_PERMISSIONS = {
    "super_admin": {"*"},
    "operations_manager": {"customers:read", "customers:write", "plans:write", "network:read"},
    "support_agent": {"customers:read", "tickets:read", "tickets:write"},
    "network_engineer": {"network:read", "network:write", "outages:write"},
    "field_technician": {"assignments:read", "assignments:write"},
    "customer": {"self:read", "self:write", "tickets:write"},
}

def require_permission(user, permission: str):
    permissions = ROLE_PERMISSIONS.get(user.role, set())
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user
