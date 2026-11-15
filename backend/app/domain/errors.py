"""Meaningful, UI-safe errors. No stack traces or secrets ever reach the client."""


class AFMError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFound(AFMError):
    status_code = 404


class Conflict(AFMError):
    status_code = 409


class Forbidden(AFMError):
    status_code = 403
