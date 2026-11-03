"""Bounded text streams for untrusted submission output."""

from typing import TextIO


class BoundedTextWriter:
    """Write at most a fixed number of UTF-8 bytes to an underlying text stream."""

    def __init__(self, stream: TextIO, limit_bytes: int) -> None:
        self.stream = stream
        self.limit_bytes = limit_bytes
        self.bytes_written = 0

    @property
    def encoding(self) -> str:
        return "utf-8"

    @property
    def errors(self) -> str:
        return "replace"

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("write() argument must be str")

        encoded = value.encode("utf-8")
        remaining = self.limit_bytes - self.bytes_written
        if remaining > 0:
            accepted = encoded[:remaining].decode("utf-8", errors="ignore")
            self.stream.write(accepted)
            written = len(accepted.encode("utf-8"))
            self.bytes_written += written
        return len(value)

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True
