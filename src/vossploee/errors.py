class AgentExecutionError(RuntimeError):
    pass


class CapabilityConfigurationError(ValueError):
    """Invalid capability enablement, config, or tool references."""
