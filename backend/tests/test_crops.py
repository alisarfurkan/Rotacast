import copy

import pytest
import yaml

from rotacast.knowledge.crops import DEFAULT_PATH, load_crops


@pytest.fixture(scope="module")
def crops():
    return load_crops()


def _raw():
    with open(DEFAULT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _write(tmp_path, data):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_loads_all(crops):
    assert len(crops) >= 20
    for cid in ("wheat_winter", "sugar_beet", "maize_grain", "chickpea", "vetch_cover", "alfalfa", "sainfoin"):
        assert cid in crops
    for c in crops.values():
        assert c.name["en"] and c.name["tr"]
        assert c.season_length_days > 0
        assert c.sources


def test_fao56_spot_checks(crops):
    assert crops["wheat_winter"].fao56.kc[1] == 1.15
    assert crops["maize_grain"].fao56.kc[1] == 1.20
    assert crops["sugar_beet"].fao56.kc[1] == 1.20
    assert crops["sugar_beet"].fao56.stage_days == (30, 45, 90, 15)
    assert crops["maize_grain"].fao56.ky == 1.25


def test_properties(crops):
    assert crops["chickpea"].is_legume
    assert crops["vetch_cover"].is_cover and crops["vetch_cover"].is_legume
    assert not crops["wheat_winter"].is_legume
    assert crops["alfalfa"].perennial_years == 3
    assert crops["wheat_winter"].perennial_years is None
    assert crops["wheat_winter"].season_length_days == sum(crops["wheat_winter"].fao56.stage_days)


def test_irrigated_is_potential(crops):
    for c in crops.values():
        y = c.economics.yield_t_ha
        assert y["irrigated"] >= y["rainfed"], c.id


def test_frozen(crops):
    with pytest.raises(Exception):
        crops["wheat_winter"].family = "x"


@pytest.mark.parametrize("mutate,field", [
    (lambda c: c["fao56"]["kc"].__setitem__(1, 2.0), "fao56.kc"),
    (lambda c: c["fao56"].__setitem__("p", 1.5), "fao56.p"),
    (lambda c: c["fao56"].__setitem__("ky", 3), "fao56.ky"),
    (lambda c: c["sowing"].__setitem__("window_doy", [0, 400]), "sowing.window_doy"),
    (lambda c: c.__setitem__("family", "Bogus"), "family"),
    (lambda c: c.__setitem__("category", "weed"), "category"),
    (lambda c: c.pop("rusle_c"), "rusle_c"),
])
def test_bad_yaml_raises(tmp_path, mutate, field):
    data = copy.deepcopy(_raw())
    mutate(data[0])
    with pytest.raises(ValueError) as ei:
        load_crops(_write(tmp_path, data))
    assert data[0]["id"] in str(ei.value) and field in str(ei.value)


def test_duplicate_id(tmp_path):
    data = _raw()
    data.append(copy.deepcopy(data[0]))
    with pytest.raises(ValueError, match="duplicate"):
        load_crops(_write(tmp_path, data))
