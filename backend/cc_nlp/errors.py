class AnalysisError(Exception):
    """Sanitized errors only. Never embed a source snippet/prompt/response."""


class AccessDenied(AnalysisError):
    pass


class ValidationRejected(AnalysisError):
    pass


class ProviderUnavailable(AnalysisError):
    pass
