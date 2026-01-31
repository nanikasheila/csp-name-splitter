class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


class LimitExceededError(ValueError):
    """Raised when input exceeds configured limits."""


class ImageReadError(RuntimeError):
    """Raised when the input image cannot be read."""


class PsdReadError(ImageReadError):
    """Backward-compatible alias for ImageReadError."""
