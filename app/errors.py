"""One error type for everything the API rejects, rendered as ErrorOut."""


class InvoiceError(Exception):
    def __init__(self, status_code: int, error: str, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details or []


class ExtractionFailed(Exception):
    """An extractor could not produce a valid invoice. `details` holds validation errors."""

    def __init__(self, message: str, details: list[dict] | None = None, not_invoice: bool = False):
        super().__init__(message)
        self.details = details or []
        self.not_invoice = not_invoice
