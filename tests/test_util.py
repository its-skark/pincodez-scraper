import pytest

from pincodez_scraper import util

SLUG_VECTORS = [
    ('Campbelbay S.O', '744302', 'campbelbay-so-744302-nicobars'),
    ('Carnicobar S.O', '744301', 'carnicobar-so-744301-nicobars'),
    ('Champin B.O', '744303', 'champin-bo-744303-nicobars'),
    ('Chowra B.O', '744303', 'chowra-bo-744303-nicobars'),
    ('Gandhinagar B.O', '744302', 'gandhinagar-bo-744302-nicobars'),
    ('Kakana B.O', '744301', 'kakana-bo-744301-nicobars'),
    ('Kapanga S.O', '744304', 'kapanga-so-744304-nicobars'),
    ('Kondul Island B.O', '744302', 'kondul-island-bo-744302-nicobars'),
    ('Lapathy B.O', '744301', 'lapathy-bo-744301-nicobars'),
    ('Little Nicobar B.O', '744302', 'little-nicobar-bo-744302-nicobars'),
    ('Mildera B.O', '744304', 'mildera-bo-744304-nicobars'),
    ('Mus B.O', '744301', 'mus-bo-744301-nicobars'),
    ('Nancowrie S.O', '744303', 'nancowrie-so-744303-nicobars'),
    ('Nehrugram B.O', '744304', 'nehrugram-bo-744304-nicobars'),
    ('Pilomilo Island B.O', '744302', 'pilomilo-island-bo-744302-nicobars'),
    ('Sawai B.O', '744301', 'sawai-bo-744301-nicobars'),
    ('Shabnamnagar B.O', '744302', 'shabnamnagar-bo-744302-nicobars'),
    ('Teressa B.O', '744303', 'teressa-bo-744303-nicobars'),
    ('Trinket B.O', '744303', 'trinket-bo-744303-nicobars'),
    ('Aerial Bay B.O', '744202', 'aerial-bay-bo-744202-north-and-middle-andaman'),
    ('Bakultala B.O', '744205', 'bakultala-bo-744205-north-and-middle-andaman'),
    ('Betapur S.O', '744201', 'betapur-so-744201-north-and-middle-andaman'),
    ('Diglipur S.O', '744202', 'diglipur-so-744202-north-and-middle-andaman'),
    ('Hathilevel B.O', '744202', 'hathilevel-bo-744202-north-and-middle-andaman'),
    ('Kadamtala S.O (North And Middle Andaman)', '744209', 'kadamtala-so-north-and-middle-andaman-744209-north-and-middle-andaman'),
    ('Kalighat B.O', '744202', 'kalighat-bo-744202-north-and-middle-andaman'),
    ('Kanchangarh B.O', '744210', 'kanchangarh-bo-744210-north-and-middle-andaman'),
    ('Kaushalyanagar B.O', '744205', 'kaushalyanagar-bo-744205-north-and-middle-andaman'),
    ('Kishorinagar B.O', '744202', 'kishorinagar-bo-744202-north-and-middle-andaman'),
    ('Laxmipur B.O', '744202', 'laxmipur-bo-744202-north-and-middle-andaman'),
    ('Long Island S.O', '744203', 'long-island-so-744203-north-and-middle-andaman'),
    ('Mayabander S.O', '744204', 'mayabander-so-744204-north-and-middle-andaman'),
    ('Mohanpur B.O', '744204', 'mohanpur-bo-744204-north-and-middle-andaman'),
    ('Navagram B.O', '744202', 'navagram-bo-744202-north-and-middle-andaman'),
    ('Nimbudera B.O', '744201', 'nimbudera-bo-744201-north-and-middle-andaman'),
    ('Nimbutala B.O', '744205', 'nimbutala-bo-744205-north-and-middle-andaman'),
    ('Oralkatcha S.O', '744210', 'oralkatcha-so-744210-north-and-middle-andaman'),
    ('Panchawati B.O', '744205', 'panchawati-bo-744205-north-and-middle-andaman'),
    ('Parnasala B.O', '744205', 'parnasala-bo-744205-north-and-middle-andaman'),
    ('Pashimsagar B.O', '744202', 'pashimsagar-bo-744202-north-and-middle-andaman'),
    ('V.Periyapatti B.O', '621302', 'vperiyapatti-bo-621302-tiruchirappalli'),
    ('Kota Muradnagar Bo', '247667', 'kota-muradnagar-bo-247667-haridwar'),
    ('Raghavapur B.O', '506301', 'raghavapur-bo-506301-jangoan'),
    ('Pukkathurai B.O', '621213', 'pukkathurai-bo-621213-tiruchirappalli'),
    ('Bohich Bo', '203395', 'bohich-bo-203395-bulandshahr'),
    ('Khanchi So', '721643', 'khanchi-so-721643-medinipur-east'),
    ('Benchinmardi B.O', '591344', 'benchinmardi-bo-591344-belagavi'),
    ('Goalkhor Bo', '816101', 'goalkhor-bo-816101-sahebganj'),
    ('Gati Bo', '206131', 'gati-bo-206131-etawah'),
    ('Chata B.O', '504103', 'chata-bo-504103-nirmal'),
    ('Kumardungi Bo', '833214', 'kumardungi-bo-833214-west-singhbhum'),
    ('Choteamabal B.O', '494224', 'choteamabal-bo-494224-bastar'),
    ('Vengarai B.O', '614628', 'vengarai-bo-614628-thanjavur'),
    ('Wadgaon Lakh B.O', '413601', 'wadgaon-lakh-bo-413601-osmanabad'),
    ('Dadaria Bo', '394630', 'dadaria-bo-394630-tapi'),
    ('Karupur Bo', '852131', 'karupur-bo-852131-supaul'),
    ('Sanai Bo', '244411', 'sanai-bo-244411-moradabad'),
    ('Lazu B.O', '792130', 'lazu-bo-792130-tirap'),
    ('Salanpur So', '713357', 'salanpur-so-713357-paschim-bardhaman'),
    ('Kalibanga B.O', '335803', 'kalibanga-bo-335803-hanumangarh'),
    ('Manonmaniam Sundaranar Univers So', '627012', 'manonmaniam-sundaranar-univers-so-627012-tirunelveli'),
    ('Tarkwari Bo', '176045', 'tarkwari-bo-176045-hamirpur'),
    ('Daliparru B.O', '521131', 'daliparru-bo-521131-krishna'),
    ('Baznagar Bo', '207402', 'baznagar-bo-207402-kasganj'),
    ('Sahangi Bo', '802203', 'sahangi-bo-802203-bhojpur'),
    ('Basmatta Bo', '813202', 'basmatta-bo-813202-banka'),
    ('Gowripatnam B.O', '534313', 'gowripatnam-bo-534313-west-godavari'),
    ('Gajminhal B.O', '591121', 'gajminhal-bo-591121-belagavi'),
    ('Vaka Bo', '680602', 'vaka-bo-680602-thrissur'),
    ('Gavarapalem B.O', '531022', 'gavarapalem-bo-531022-visakhapatanam'),
    ('Pydigudem B.O', '507137', 'pydigudem-bo-507137-bhadradri-kothagudem'),
    ('Pala B.O', '793200', 'pala-bo-793200-east-jaintia-hills'),
    ('Ulianallore Bo', '631052', 'ulianallore-bo-631052-ranipet'),
    ('Belgram Bo', '742168', 'belgram-bo-742168-murshidabad'),
    ('Hongalli B.O', '571111', 'hongalli-bo-571111-chamarajanagara'),
    ('Khutahan Khas Bo', '273306', 'khutahan-khas-bo-273306-gorakhpur'),
    ('Payyoli So', '673522', 'payyoli-so-673522-kozhikode'),
    ('Devarjan B.O', '413517', 'devarjan-bo-413517-latur'),
    ('Sinhachawar Bo', '221701', 'sinhachawar-bo-221701-ballia'),
    ('Damarapakam B.O', '517591', 'damarapakam-bo-517591-chittoor'),
    ('Janakpur Bo', '848114', 'janakpur-bo-848114-samastipur'),
    ('Tellurarni Bo', '632313', 'tellurarni-bo-632313-tiruvannamalai'),
    ('Vizora B.O', '444401', 'vizora-bo-444401-akola'),
    ('Dholia B.O', '341304', 'dholia-bo-341304-nagaur'),
    ('Raipur Ganj Bo', '261135', 'raipur-ganj-bo-261135-sitapur'),
    ('Jeena Bo', '821310', 'jeena-bo-821310-rohtas'),
    ('Lakhanwas B.O', '473115', 'lakhanwas-bo-473115-guna'),
    ('Mhate Bk B.O', '415012', 'mhate-bk-bo-415012-satara'),
    ('Ayur So', '691533', 'ayur-so-691533-kollam'),
    ('Singhirampur Bo', '209724', 'singhirampur-bo-209724-farrukhabad'),
    ('Ainpur B.O', '425507', 'ainpur-bo-425507-jalgaon'),
    ('Chintapalli S.O', '531111', 'chintapalli-so-531111-visakhapatanam'),
    ('Garmohini Bo', '851203', 'garmohini-bo-851203-khagaria'),
    ('Nanoli Bo', '262522', 'nanoli-bo-262522-pithoragarh'),
    ('Poksari Bo', '497101', 'poksari-bo-497101-surguja'),
    ('Aklera S.O', '326033', 'aklera-so-326033-jhalawar'),
    ('Dhodhagaon Bo', '497111', 'dhodhagaon-bo-497111-surguja'),
    ('Vaijpur Settelement B.O', '425107', 'vaijpur-settelement-bo-425107-jalgaon'),
    ('Chandras B.O', '311402', 'chandras-bo-311402-bhilwara'),
    ('T Jalalpur Bo', '824235', 't-jalalpur-bo-824235-gaya'),
]

@pytest.mark.parametrize("name,pincode,expected_slug", SLUG_VECTORS)
def test_bulk_slug_is_derivable(name, pincode, expected_slug):
    body = expected_slug.rsplit(f"-{pincode}-", 1)
    district_key = body[1]
    assert util.post_office_slug(name, pincode, district_key) == expected_slug


@pytest.mark.parametrize("name,pincode,expected_slug", SLUG_VECTORS)
def test_id_prefix_roundtrip(name, pincode, expected_slug):
    assert util.post_office_id(expected_slug).startswith("pz:po:")


def test_slugify_drops_punctuation():
    assert util.slugify("Atmakur(Atp) S.O") == "atmakuratp-so"
    assert util.slugify("Bandra West S.O") == "bandra-west-so"
    assert util.slugify("P&T Colony S.O") == "pt-colony-so"
    assert util.slugify("K/Nokno B.O") == "knokno-bo"
    assert util.slugify("Raja,Mpalli B.O") == "rajampalli-bo"


def test_district_and_state_slugs():
    assert util.district_slug("Gurugram", "Haryana") == "gurugram-haryana"
    assert util.district_slug("New Delhi", "Delhi") == "new-delhi-delhi"
    assert util.district_slug("Central", "Delhi") == "central-delhi"
    assert util.state_slug("Andaman And Nicobar Islands") == "andaman-and-nicobar-islands"


def test_numeric_helpers():
    assert util.to_float("") is None
    assert util.to_float("28.60612") == 28.60612
    assert util.to_float(None) is None
    assert util.to_int("23") == 23
    assert util.to_int("") is None
    assert util.to_int(None) is None
