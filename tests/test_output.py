from io import StringIO

from runner.output import BoundedTextWriter


def test_bounded_writer_truncates_at_utf8_byte_limit() -> None:
    stream = StringIO()
    writer = BoundedTextWriter(stream, limit_bytes=4)

    assert writer.write("abéxyz") == 6
    writer.flush()

    assert stream.getvalue() == "abé"
    assert writer.bytes_written == 4


def test_bounded_writer_discards_writes_after_limit() -> None:
    stream = StringIO()
    writer = BoundedTextWriter(stream, limit_bytes=4)

    writer.write("1234")
    writer.write("5678")

    assert stream.getvalue() == "1234"
    assert writer.bytes_written == 4
