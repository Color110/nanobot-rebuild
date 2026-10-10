class MCPRuntimeError(RuntimeError):
    pass


class MCPStateError(MCPRuntimeError):
    pass


class MCPTimeoutError(MCPRuntimeError):
    pass


class MCPTransportError(MCPRuntimeError):
    pass
class MCPSecurityError(MCPRuntimeError):
    pass