from enum import StrEnum
class MCPClientState(StrEnum):
    READY = "READY"
    FAILED = "FAILED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
