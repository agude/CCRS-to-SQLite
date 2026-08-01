import pytest

from ccrs_to_sqlite import __version__
from ccrs_to_sqlite.main import DEFAULT_OUTPUT_FILE, build_parser, main


def test_version_flag_prints_the_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_input_arguments_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2


def test_output_file_defaults_when_not_given():
    arguments = build_parser().parse_args(["some_dir"])

    assert arguments.output_file == DEFAULT_OUTPUT_FILE


def test_file_flags_accumulate():
    arguments = build_parser().parse_args(
        ["--crashes", "a.csv", "--crashes", "b.csv", "--parties", "p.csv"]
    )

    assert [path.name for path in arguments.crashes] == ["a.csv", "b.csv"]
    assert [path.name for path in arguments.parties] == ["p.csv"]
    assert arguments.injured == []


@pytest.mark.parametrize("argv", [["some_dir"], ["--crashes", "crashes_2025.csv"]])
def test_conversion_is_not_implemented_yet(argv, capsys):
    assert main(argv) == 1
    assert "not implemented" in capsys.readouterr().err
