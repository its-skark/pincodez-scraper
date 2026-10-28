import pytest

from pincodez_scraper.sources import pages

DISTRICT_HTML = """
<html><body>
<script>
document.addEventListener('DOMContentLoaded', () => {
    const districtData = {"name":"Gurugram","slug":"gurugram-haryana","state_name":"Haryana"};
    const pincodesData = [{"pincode":"122001","total_post_offices":1}];
    const subdistrictsData = [{"name":"Badshahpur St"},{"name":"Farrukhnagar"},{"name":"Gurgaon"}];
});
</script>
</body></html>
"""

EMPTY_DISTRICT_HTML = """
<html><body><script>
const subdistrictsData = [];
</script></body></html>
"""

PIN_HTML = """
<table class="data-table table-cards">
<thead><tr><th>Office Name</th><th>Type</th><th>Delivery</th><th>Sub-District / Taluk</th>
<th>DIGIPIN</th><th>Coordinates</th></tr></thead>
<tbody>
<tr>
  <td class="primary-cell" data-label="Office Name">
    <a href="/post-offices/gurgaon-ho-122001-gurugram"><strong>Gurgaon Ho</strong></a>
  </td>
  <td data-label="Type"><span class="badge">HO</span></td>
  <td data-label="Delivery"><span class="badge badge-po">Delivery</span></td>
  <td data-label="Sub-District / Taluk">Gurugram</td>
  <td class="text-mono" data-label="DIGIPIN">39JLJ69353</td>
  <td>28.462000°, 77.031639°</td>
</tr>
<tr>
  <td class="primary-cell" data-label="Office Name">
    <a href="/post-offices/arjun-nagar-so-122001-gurugram"><strong>Arjun Nagar So</strong></a>
  </td>
  <td data-label="Type"><span class="badge">PO</span></td>
  <td data-label="Delivery"><span class="badge badge-neutral">Non-Delivery</span></td>
  <td data-label="Sub-District / Taluk">Gurugram</td>
  <td class="text-mono" data-label="DIGIPIN">39JLJ5CTJC</td>
  <td>28.461083°, 77.021472°</td>
</tr>
</tbody></table>
"""


def test_parse_subdistricts_from_inline_json():
    assert pages.parse_subdistricts(DISTRICT_HTML) == ["Badshahpur St", "Farrukhnagar", "Gurgaon"]


def test_parse_subdistricts_empty():
    assert pages.parse_subdistricts(EMPTY_DISTRICT_HTML) == []


def test_parse_subdistricts_missing():
    assert pages.parse_subdistricts("<html><body>nothing here</body></html>") == []


def test_parse_pin_taluk_column():
    rows = pages.parse_pin_taluk_column(PIN_HTML)
    assert len(rows) == 2
    assert rows[0]["name"] == "Gurgaon Ho"
    assert rows[0]["taluk"] == "Gurugram"
    assert rows[1]["taluk"] == "Gurugram"


def test_parse_pin_office_rows():
    rows = pages.parse_pin_office_rows(PIN_HTML)
    assert len(rows) == 2
    assert rows[0]["office_type"] == "HO"
    assert rows[0]["delivery_status"] == "Delivery"
    assert rows[0]["digipin"] == "39JLJ69353"
    assert rows[0]["latitude"] == pytest.approx(28.462)
    assert rows[0]["longitude"] == pytest.approx(77.031639)
    assert rows[1]["office_type"] == "PO"
    assert rows[1]["delivery_status"] == "Non-Delivery"
