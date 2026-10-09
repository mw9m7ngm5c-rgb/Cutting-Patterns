import pytest

import cli
from conftest import FIXTURES
from importers import simsaw


def test_inputs_import(ngomi_inputs):
    ds = ngomi_inputs
    assert len(ds.logs) == 200 and len(ds.log_classes) == 5 and len(ds.patterns) == 3
    assert sum(c.valid for c in ds.products.combinations) == 13          # 25x114, 50x102 and 50x114 are off
    assert not ds.products.is_valid(25, 114) and ds.products.is_valid(25, 102)
    assert ds.products.wane_rule(19, 76).thickness_pct == 10 and ds.products.wane_rule(19, 76).width_pct == 30
    assert ds.products.price(38, 114, 2400) == 4000.0


def test_units_are_converted_at_the_boundary(ngomi_inputs):
    log = next(g for g in ngomi_inputs.logs if g.no == 8)
    assert (log.sed_cm, log.length_m, log.sweep_mm) == (21.4, 2.7, 9.2)   # stored as single-precision floats
    assert log.sweep_mm_per_m == pytest.approx(9.2 / 2.7)                 # classes compare mm per metre
    assert max(g.sweep_mm_per_m for g in ngomi_inputs.logs) <= 15.0 + 1e-6


def test_logs_fall_into_classes_by_their_properties(ngomi_inputs):
    counts = [len(ngomi_inputs.logs_in_class(c.no)) for c in ngomi_inputs.log_classes]
    assert counts == [36, 34, 30, 44, 48]
    assert 200 - sum(counts) == 8                                          # 17.0 to 17.9 cm: no class


def test_run_snapshot_is_read_with_its_own_keys(ngomi_run):
    products = {(b.thickness, b.width) for b in ngomi_run.board_results}
    assert (25, 114) not in products and (25, 102) in products
    assert len(ngomi_run.dataset.logs) == 70
    for b in ngomi_run.board_results[:50]:
        t = ngomi_run.dataset.products.thickness(b.thickness)
        w = ngomi_run.dataset.products.width(b.width)
        assert b.dry_volume == pytest.approx(t.dry * w.dry * b.length_m / 1e6, abs=1e-8)


def test_template_dataset_imports():
    ds = simsaw.load_inputs(FIXTURES / "template")
    assert [(p.primary, p.secondary) for p in ds.patterns] == [("25/76/25", "5*25")]
    assert ds.lines[0].primary_kerf == 5.0 and ds.lines[0].edger_blades == 2
    assert simsaw.run_names(FIXTURES / "template") == []
    with pytest.raises(ValueError):
        simsaw.load_run(FIXTURES / "template")


def test_cli_validate_passes(capsys):
    assert cli.main(["validate", "--dataset", str(FIXTURES / "ngomi_1"), "--run", "Test1"]) == 0
    out = capsys.readouterr().out
    assert "within tolerance" in out and "265/265" in out


def test_cli_simulate_one_pattern(capsys):
    code = cli.main(["simulate", "--dataset", str(FIXTURES / "ngomi_1"), "--pattern", "25/114/25", "2*19 3*38 3*19",
                     "--log", "8", "--boards", "--mix", "--volumes"])
    out = capsys.readouterr().out
    assert code == 0 and "38x114x2.7m" in out and "0.105927" in out and "Sawdust" in out


def test_cli_simulate_whole_dataset(capsys):
    assert cli.main(["simulate", "--dataset", str(FIXTURES / "ngomi_1")]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") >= 5 and "19 25 38 50 38 25 19" in out


def test_cli_pattern_needs_logs(capsys):
    assert cli.main(["simulate", "--dataset", str(FIXTURES / "ngomi_1"), "--pattern", "25/114/25", "3*38"]) == 2
