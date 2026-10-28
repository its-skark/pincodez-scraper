import pytest

from pincodez_scraper import digipin

ENCODE_VECTORS = [
    (28.622788, 77.213033, '39J49LL8T4'),
    (19.076, 72.8777, '4FK5958823'),
    (15.3173, 75.7139, '4439T355P7'),
    (28.4595, 77.0266, '39JLJ6JKC5'),
    (28.60612, 77.220929, '39J423KPJ8'),
    (29.0, 70.0, 'J98PK8PK8P'),
    (37.5, 85.0, '9C2L82L82L'),
    (9.0, 70.0, 'L282L82L82'),
    (19.0, 70.0, 'K965K65K65'),
    (37.5, 98.5, '882L82L82L'),
    (4.0, 80.0, 'MT33333333'),
    (4.0, 85.0, 'PM2J72J72J'),
    (34.0, 85.0, '93PLTPLTPL'),
    (24.0, 75.0, '34JM8JM8JM'),
    (4.0, 95.0, 'TPJJJJJJJJ'),
    (14.0, 98.5, '66PK8PK8PK'),
    (24.0, 90.0, '267LC7LC7L'),
    (37.5, 75.0, 'CCJM8JM8JM'),
    (24.0, 65.0, 'JK2P92P92P'),
    (9.0, 90.0, 'P78JM8JM8J'),
    (4.0, 75.0, 'MMJ37J37J3'),
    (4.0, 90.0, 'PT7J37J37J'),
    (19.0, 80.0, '4844444444'),
    (19.0, 75.0, '4CK46K46K4'),
    (37.5, 70.0, 'F97PF7PF7P'),
    (9.0, 98.5, 'T79JT9JT9J'),
    (29.0, 98.5, '789L69L69L'),
    (24.0, 80.0, '363MC3MC3M'),
    (29.0, 95.0, '79FLKFLKFL'),
]

DECODE_VECTORS = [
    ('39J423KPJ8', 28.606091, 77.220928, 28.606108, 77.220945),
    ('39J49LL8T4', 28.622776, 77.213032, 28.622793, 77.213049),
    ('4FK5958823', 19.075966, 72.877689, 19.075983, 72.877707),
    ('4439T355P7', 15.317268, 75.713879, 15.317286, 75.713896),
    ('39JLJ6JKC5', 28.459492, 77.026573, 28.459509, 77.02659),
    ('3C7T6TK7J7', 28.413795, 76.992962, 28.413813, 76.992979),
]


@pytest.mark.parametrize("lat,lon,expected", ENCODE_VECTORS)
def test_encode_matches_live_api(lat, lon, expected):
    assert digipin.encode(lat, lon) == expected


@pytest.mark.parametrize("code,min_lat,min_lon,center_lat,center_lon", DECODE_VECTORS)
def test_decode_matches_live_api(code, min_lat, min_lon, center_lat, center_lon):
    result = digipin.decode(code)
    assert abs(result["min_latitude"] - min_lat) < 2e-6
    assert abs(result["min_longitude"] - min_lon) < 2e-6
    assert abs(result["center_latitude"] - center_lat) < 2e-6
    assert abs(result["center_longitude"] - center_lon) < 2e-6


def test_round_trip_contains_point():
    for lat, lon, code in ENCODE_VECTORS:
        result = digipin.decode(code)
        assert result["min_latitude"] <= lat <= result["max_latitude"]
        assert result["min_longitude"] <= lon <= result["max_longitude"]


def test_code_shape():
    alphabet = set("23456789CJKLMPFT")
    for lat, lon, code in ENCODE_VECTORS:
        assert len(code) == 10
        assert set(code) <= alphabet


def test_out_of_range_rejected():
    with pytest.raises(digipin.DigipinError):
        digipin.encode(1.0, 70.0)
    with pytest.raises(digipin.DigipinError):
        digipin.encode(20.0, 50.0)


def test_invalid_code_rejected():
    with pytest.raises(digipin.DigipinError):
        digipin.decode("SHORT")
    with pytest.raises(digipin.DigipinError):
        digipin.decode("!!!!!!!!!!")
