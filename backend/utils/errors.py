class AppError(Exception):
    """An expected error. main.py turns it into {"error": message} with this status code."""

    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
