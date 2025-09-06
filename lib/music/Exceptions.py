class MusicError(Exception):
    """Base exception for music-related errors."""

    pass


class UserError(MusicError):
    """Exception raised for user-related, expected errors."""

    pass


class InternalError(MusicError):
    """Exception raised for internal, unexpected errors."""

    pass
