class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


class LimitExceededError(ValueError):
    """Raised when input exceeds configured limits."""


class ImageMagickNotFoundError(RuntimeError):
    """Raised when ImageMagick is unavailable."""


class PsdReadError(RuntimeError):
    """Raised when the PSD cannot be read."""
