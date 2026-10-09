import pytest

from tess_hunt.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "tess-hunt 0.1.0" in capsys.readouterr().out
