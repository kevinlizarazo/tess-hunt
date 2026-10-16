from fakes import FakeResponse, FakeSession

from tess_hunt import literature

ZENODO_JSON = (
    b'{"hits": {"hits": [{"id": 23175179, "metadata": {"title": "TIC 4206066 predictions"}}]}}'
)
ARXIV_XML = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2610.00001v1</id><title>A planet around TIC 4206066</title></entry></feed>"""
OPENALEX_JSON = b'{"results": [{"id": "https://openalex.org/W1", "title": "TIC 4206066 b"}]}'


def test_search_collects_hits_from_each_service():
    session = FakeSession(
        routes={
            literature.ZENODO: ZENODO_JSON,
            literature.ARXIV: ARXIV_XML,
            literature.OPENALEX: OPENALEX_JSON,
        }
    )
    out = literature.search(4206066, session, pause=0.0)
    assert out["zenodo"]["hits"][0]["title"] == "TIC 4206066 predictions"
    assert out["arxiv"]["hits"][0]["id"].endswith("2610.00001v1")
    assert out["openalex"]["hits"][0]["title"] == "TIC 4206066 b"


def test_a_failing_service_is_recorded_not_raised():
    session = FakeSession(
        sequence=[FakeResponse(503)],
        routes={literature.ARXIV: ARXIV_XML, literature.OPENALEX: OPENALEX_JSON},
    )
    out = literature.search(1, session, pause=0.0)
    assert out["zenodo"]["status"] == "error" and out["arxiv"]["status"] == "ok"
