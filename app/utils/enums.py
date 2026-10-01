from enum import Enum
class SIMStatus(str, Enum):
    AVAILABLE="available"
    ACTIVE="active"
    SUSPENDED="suspended"
    LOST="lost"
    BLOCKED="blocked"
    DEACTIVATED="deactivated"
