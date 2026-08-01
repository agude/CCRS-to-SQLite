import csv
import gzip

import pytest

from ccrs_to_sqlite.open_record import is_gzipped, open_source_file

CSV_TEXT = 'Collision Id,Report Number\r\n4550266,"9680-2025-00147"\r\n'


def write_plain(directory, name, text=CSV_TEXT, encoding="utf-8"):
    path = directory / name
    path.write_bytes(text.encode(encoding))
    return path


def write_gzipped(directory, name, text=CSV_TEXT, encoding="utf-8"):
    path = directory / name
    path.write_bytes(gzip.compress(text.encode(encoding)))
    return path


def test_is_gzipped_distinguishes_the_two_encodings(tmp_path):
    assert is_gzipped(write_gzipped(tmp_path, "crashes.csv.gz"))
    assert not is_gzipped(write_plain(tmp_path, "crashes.csv"))


def test_is_gzipped_reads_an_empty_file_as_plain(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")

    assert not is_gzipped(empty)


@pytest.mark.parametrize("write_file", [write_plain, write_gzipped])
def test_open_source_file_reads_both_forms_identically(tmp_path, write_file):
    path = write_file(tmp_path, "crashes.csv")

    with open_source_file(path) as source_file:
        rows = list(csv.reader(source_file))

    assert rows == [["Collision Id", "Report Number"], ["4550266", "9680-2025-00147"]]


def test_compression_is_detected_from_content_not_from_the_suffix(tmp_path):
    """A gzipped file named .csv still loads, and vice versa."""
    misnamed = write_gzipped(tmp_path, "crashes_2025.csv")

    with open_source_file(misnamed) as source_file:
        assert source_file.readline().rstrip("\r\n") == "Collision Id,Report Number"


@pytest.mark.parametrize("write_file", [write_plain, write_gzipped])
def test_a_byte_order_mark_is_not_part_of_the_first_header_cell(tmp_path, write_file):
    path = write_file(tmp_path, "crashes.csv", encoding="utf-8-sig")

    with open_source_file(path) as source_file:
        header = next(csv.reader(source_file))

    assert header[0] == "Collision Id"


def test_embedded_newlines_inside_quoted_fields_survive(tmp_path):
    path = write_plain(tmp_path, "crashes.csv", text='Sketch\r\n"line one\r\nline two"\r\n')

    with open_source_file(path) as source_file:
        rows = list(csv.reader(source_file))

    assert rows[1] == ["line one\r\nline two"]


def test_undecodable_bytes_are_fatal_by_default(tmp_path):
    path = tmp_path / "crashes.csv"
    path.write_bytes(b"Make\r\nMERCEDES-BE\xffZ\r\n")

    with open_source_file(path) as source_file, pytest.raises(UnicodeDecodeError):
        source_file.read()


@pytest.mark.parametrize(("parse_error", "expected"), [("ignore", "MERZ"), ("replace", "MER�Z")])
def test_undecodable_bytes_can_be_dropped_or_replaced(tmp_path, parse_error, expected):
    path = tmp_path / "crashes.csv"
    path.write_bytes(b"Make\r\nMER\xffZ\r\n")

    with open_source_file(path, parse_error=parse_error) as source_file:
        rows = list(csv.reader(source_file))

    assert rows[1] == [expected]


def test_an_unknown_parse_error_mode_is_rejected(tmp_path):
    path = write_plain(tmp_path, "crashes.csv")

    with pytest.raises(ValueError, match="parse_error must be one of"):
        open_source_file(path, parse_error="surrogateescape")
