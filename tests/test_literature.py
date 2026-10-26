import json
import os
import re
from urllib.parse import unquote

import pytest
import requests
import test_vetting as tv
from fakes import FakeResponse, FakeSession

from tess_hunt import literature, vetting
from tess_hunt.checks import Outcome
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.provenance import sha256_file

ZENODO_JSON = (
    b'{"hits": {"hits": [{"id": 23175179, "metadata": {"title": "TIC 4206066 predictions"}}]}}'
)
ARXIV_XML = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2610.00001v1</id><title>A planet around TIC 4206066</title></entry></feed>"""
OPENALEX_JSON = b'{"results": [{"id": "https://openalex.org/W1", "title": "TIC 4206066 b"}]}'

CFG = load_criteria(tv.VET3)["literature"]
TIC = 164767175
# SIMBAD TAP's answer for TIC 164767175 on 2026-10-17, spacing as served.
SIMBAD_IDS = [
    "TIC 164767175",
    "HIP 8152",
    "Gaia DR3 5140454049422547200",
    "2MASS J01445032-1824032",
    "BD-19   302",
    "CPD-19   182",
    "GSC 05855-02286",
    "HIC   8152",
    "TOI-266",
    "PPM 210598",
    "SAO 147995",
    "TYC 5855-2286-1",
    "YZ 108   471",
    "uvby98 -001900302",
    "RAVE J014450.3-182403",
    "Gaia DR1 5140454045126761984",
    "Gaia DR2 5140454049422547200",
]
EXOFOP = {
    "basic_info": {"tic_id": str(TIC), "confirmed_planets": "HIP 8152 b, HIP 8152 c"},
    "coordinates": {"ra": "26.2096"},
    "tois": [
        {"toi": "TOI 266.01", "disp_tfop": "CP", "notes": "a note on TOI 266.01"},
        {"toi": "TOI 266.02", "disp_tfop": "CP", "notes": ""},
    ],
    "ctois": [
        {"ctoi": "TIC 164767175.03", "cdisp": "PC", "cnotes": "single transit", "paper": "a paper"}
    ],
    "imaging": [
        {"itel": "Gemini (8 m)", "iinst": "'Alopeke", "itype": "Speckle", "icont": "4.49 @ 0.5"}
    ],
    "spectroscopy": [{"stel": "SMARTS"}],
    # Each provenance heading, then its rows, as served on 2026-10-17 (fields trimmed).
    "planet_parameters": [
        {
            "prov": "confirmed",
            "prov_title": "Confirmed Planets (Exoplanet Archive)",
            "prov_num": "1",
        },
        {
            "prov": None,
            "name": "HIP 8152 b",
            "toi": "",
            "disp": "",
            "epoch": "2458393.0855",
            "per": "10.751014",
            "dur": "2.9954278382616",
        },
        {"prov": "ctoi", "prov_title": "Planet Parameters (User uploaded)", "prov_num": "1"},
        {
            "prov": None,
            "name": "TIC 164767175.01",
            "toi": "TOI 266.01",
            "disp": "PC",
            "epoch": "2459176.2933",
            "per": None,
            "dur": "8.2",
        },
    ],
    "files": [
        {"ftype": "Light_Curve", "fname": "TIC164767175-01_PEST.zip", "fid": "26009"},
        {"ftype": "Image", "fname": "TOI266I-dc20191015-562.dat", "fid": "15997"},
    ],
}
SERVICES = {
    literature.SIMBAD_TAP: "simbad",
    literature.ARXIV: "arxiv",
    literature.OPENALEX: "openalex",
    literature.ZENODO: "zenodo",
    literature.ADS: "ads",
    literature.ADS_OBJECTS: "objects",
    literature.EXOFOP_TARGET: "exofop",
}
# ADS's object service's answer for TIC 164767175 on 2026-10-19: SIMBAD's id for the star, and "0" from NED.
SIMBID = "1289183"
QUERY = '((=abs:"TIC 164767175" OR simbid:"1289183" OR nedid:"0") database:astronomy)'
ATOM = (
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" '
    'xmlns:arxiv="http://arxiv.org/schemas/atom">'
)
TOKEN = "ads-token-k3v1n-7f2a"
LOOKUP = f"{literature.OPENALEX}/doi:"


def paper(title: str, doi: str | None = None, arxiv: str | None = None) -> dict:
    return {"title": title, "doi": doi, "arxiv": arxiv}


AKANA = paper(
    "The TESS-Keck Survey. XVI. Mass Measurements for 12 Planets in Eight Systems",
    arxiv="2306.16587",
)


def atom(entries: list[dict], total: int) -> bytes:
    items = "".join(
        f"<entry><id>http://arxiv.org/abs/{p['arxiv']}v2</id><title>{p['title']}</title>"
        + (f"<arxiv:doi>{p['doi']}</arxiv:doi>" if p["doi"] else "")
        + "</entry>"
        for p in entries
    )
    return (
        f"{ATOM}<opensearch:totalResults>{total}</opensearch:totalResults>{items}</feed>".encode()
    )


class Web:
    """The services the literature search reads. `hits` maps (service, name) to papers; `status` maps a service, or
    (service, name), to the HTTP status it answers instead. ADS's object service resolves a star SIMBAD holds in
    `names`. ADS answers only the bearer `token`. OpenAlex's work by DOI ("lookup") answers with `titles` (DOI to
    title, None for a work without one), and 404 for any other DOI."""

    def __init__(self, hits=None, status=None, names=None, token=TOKEN, titles=None):
        self.hits = hits or {}
        self.status = status or {}
        self.names = {TIC: SIMBAD_IDS} if names is None else names
        self.token = token
        self.titles = titles or {}
        self.calls = []

    def get(self, url, timeout, params=None, headers=None):
        if url.startswith(LOOKUP):
            return self.answer("lookup", "doi", {"doi": unquote(url.removeprefix(LOOKUP))}, headers)
        return self.answer(SERVICES[url], "params", dict(params or {}), headers)

    def post(self, url, timeout, json=None, headers=None):
        return self.answer(SERVICES[url], "body", json, headers)

    def answer(self, service: str, kind: str, sent: dict, headers: dict | None) -> FakeResponse:
        name = self.name(service, sent)
        self.calls.append(
            {"service": service, "name": name, kind: sent, "headers": dict(headers or {})}
        )
        status = self.status.get((service, name), self.status.get(service))
        if status:
            return FakeResponse(status)
        bearer = (headers or {}).get("Authorization") == f"Bearer {self.token}"
        if service in ("ads", "objects") and not bearer:
            return FakeResponse(401)
        if service == "lookup" and name not in self.titles:
            return FakeResponse(404)
        return FakeResponse(200, getattr(self, service)(name, sent))

    @staticmethod
    def name(service: str, sent: dict) -> str:
        if service == "lookup":
            return sent["doi"]
        if service == "simbad":
            return re.search(r"'(TIC \d+)'", sent["QUERY"]).group(1)
        if service == "exofop":
            return f"TIC {sent['id']}"
        if service == "objects":
            [query] = sent["query"]
            return re.fullmatch(r'object:"(.*)"', query).group(1)
        if service == "ads":
            return re.search(r'=abs:"(.*?)"', sent["q"]).group(1)
        key = {"arxiv": "search_query", "openalex": "filter", "zenodo": "q"}[service]
        return re.search(r'"(.*)"', sent[key]).group(1)

    def page(self, service: str, name: str, start: int, size: int) -> tuple[list[dict], int]:
        found = self.hits.get((service, name), [])
        return found[start : start + size], len(found)

    def simbad(self, name, params):
        ids = self.names.get(int(name.split()[1]), [])
        return json.dumps({"metadata": [{"name": "id"}], "data": [[i] for i in ids]}).encode()

    def arxiv(self, name, params):
        return atom(*self.page("arxiv", name, params["start"], params["max_results"]))

    def openalex(self, name, params):
        size = params["per-page"]
        found, total = self.page("openalex", name, (params["page"] - 1) * size, size)
        results = [
            {
                "id": f"https://openalex.org/W{i}",
                "title": p["title"],
                "doi": f"https://doi.org/{p['doi']}" if p["doi"] else None,
            }
            for i, p in enumerate(found)
        ]
        return json.dumps({"meta": {"count": total}, "results": results}).encode()

    def zenodo(self, name, params):
        size = params["size"]
        found, total = self.page("zenodo", name, (params["page"] - 1) * size, size)
        records = [
            {"id": 1000 + i, "doi": p["doi"], "metadata": {"title": p["title"]}}
            for i, p in enumerate(found)
        ]
        return json.dumps({"hits": {"total": total, "hits": records}}).encode()

    def objects(self, name, body):
        simbid = SIMBID if self.names.get(int(name.split()[1])) else "0"
        query = f'((=abs:"{name}" OR simbid:"{simbid}" OR nedid:"0") database:astronomy)'
        return json.dumps({"query": query}).encode()

    def ads(self, name, params):
        found, total = self.page("ads", name, params["start"], params["rows"])
        docs = [
            {
                "bibcode": f"2023AJ....166..{150 + i}A",
                "title": [p["title"]],
                **({"doi": [p["doi"]]} if p["doi"] else {}),
                "identifier": [f"arXiv:{p['arxiv']}"] if p["arxiv"] else [],
            }
            for i, p in enumerate(found)
        ]
        return json.dumps({"response": {"numFound": total, "docs": docs}}).encode()

    def exofop(self, name, params):
        return json.dumps(EXOFOP).encode()

    def lookup(self, doi, sent):
        return json.dumps(
            {"id": f"https://openalex.org/W{len(doi)}", "title": self.titles[doi]}
        ).encode()


@pytest.fixture(autouse=True)
def slept(request, monkeypatch):
    """No unit test waits out arXiv's pause or a retry's backoff; each wait is recorded instead."""
    waits = []
    if not request.node.get_closest_marker("network"):
        monkeypatch.setattr(literature.time, "sleep", waits.append)
    return waits


def search(web, names=("TIC 164767175", "HIP 8152"), token=TOKEN, cfg=CFG, done=None) -> dict:
    # SIMBAD's record as `vetting literature` passes it: whether SIMBAD knows the star decides how ADS's "0" reads.
    simbad = literature.simbad_record(TIC, web)
    return literature.search_all(TIC, list(names), web, token, cfg, done, simbad=simbad)


def complete(record: dict) -> dict:
    """The record as `vetting literature` writes it, with SIMBAD answered."""
    return {"simbad": {"status": "ok", "names": SIMBAD_IDS, "error": None}, **record}


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


def test_simbad_names_reads_every_identifier():
    web = Web()
    assert literature.simbad_names(TIC, web) == SIMBAD_IDS
    [call] = web.calls
    assert call["params"]["FORMAT"] == "json" and "oidref" in call["params"]["QUERY"]
    # SIMBAD answered; the star is just not in it.
    assert literature.simbad_names(1, web) == []
    with pytest.raises(literature.LiteratureError, match="HTTP 503"):
        literature.simbad_names(TIC, Web(status={"simbad": 503}))
    failed = Web(status={"simbad": 400})
    assert literature.simbad_record(TIC, failed) == {
        "status": "error",
        "names": [],
        "error": "SIMBAD: HTTP 400",
    }
    # A bad request is not retried.
    assert len(failed.calls) == 1


def test_searchable_forms_and_fallback_names():
    star = {"tic": TIC, "dr3_source_id": 5140454049422547200}
    assert literature.searchable(SIMBAD_IDS, star, CFG["forms"]) == [
        "TIC 164767175",
        "HIP 8152",
        "Gaia DR3 5140454049422547200",
        "2MASS J01445032-1824032",
        "TOI-266",
        "TYC 5855-2286-1",
    ]
    # Whitespace normalised; HDE, ** and the like are not forms papers use; the TIC from the row.
    simbad = ["HD  14989", "HDE 14989", "WDS J09474-3953A", "** WG 128A", "TOI-4298"]
    assert literature.searchable(simbad, {"tic": 146282666}, CFG["forms"]) == [
        "HD 14989",
        "WDS J09474-3953A",
        "TOI-4298",
        "TIC 146282666",
    ]
    # SIMBAD failed or lacks the star: the TIC and Gaia DR3 names from the targets row.
    row = {"tic": 1, "dr3_source_id": 42}
    assert literature.searchable([], row, CFG["forms"]) == ["TIC 1", "Gaia DR3 42"]
    # A control's row has no source id; an id rounded through a float would name another star.
    for missing in (None, float("nan"), 5.140454049422547e18):
        assert literature.searchable([], {"tic": 1, "dr3_source_id": missing}, CFG["forms"]) == [
            "TIC 1"
        ]
    # Only the forms the criteria list.
    assert literature.searchable(SIMBAD_IDS, star, ["HIP"]) == ["HIP 8152"]


def test_paging_stops_at_max_hits_as_too_broad():
    cfg = {**CFG, "max_hits": 30}
    many = [paper(f"Paper {i}", f"10.1/{i}", f"2601.{i:05d}") for i in range(40)]
    web = Web(hits={("zenodo", "HIP 8152"): many[:30], ("zenodo", "TIC 164767175"): many})
    zenodo = search(web, cfg=cfg)["sources"]["zenodo"]

    def pages(name):
        return [
            c["params"]["page"] for c in web.calls if c["service"] == "zenodo" and c["name"] == name
        ]

    # Zenodo serves 25 a page without a key, so 30 hits take two pages.
    assert zenodo["HIP 8152"]["status"] == "ok" and len(zenodo["HIP 8152"]["hits"]) == 30
    assert pages("HIP 8152") == [1, 2]
    # More than max_hits stops at the first page that says so, too broad and not incomplete.
    assert zenodo["TIC 164767175"] == {
        "status": "too_broad",
        "hits": [],
        "total": 40,
        "error": None,
    }
    assert pages("TIC 164767175") == [1]
    arxiv = [c["params"]["max_results"] for c in web.calls if c["service"] == "arxiv"]
    assert arxiv == [30, 30]
    check = literature.literature_check(complete(search(web, cfg=cfg)))
    assert check.outcome == Outcome.PASS
    assert check.evidence["too_broad"] == ["zenodo TIC 164767175: 40 hits"]
    assert check.reason == "complete: 30 hits to screen"


def test_ads_too_broad_leaves_the_search_incomplete():
    cfg = {**CFG, "max_hits": 3}
    many = [paper(f"Paper {i}", f"10.1/{i}", f"2601.{i:05d}") for i in range(5)]
    # A well-studied star: every search too broad, so no hit would be left to read.
    names = ("TIC 164767175", "HIP 8152")
    hits = {(s, n): many for s in ("arxiv", "openalex", "zenodo") for n in names}
    record = search(Web(hits={**hits, ("ads", "TIC 164767175"): many}), names=names, cfg=cfg)
    assert record["sources"]["ads"]["TIC 164767175"]["status"] == "too_broad"
    check = literature.literature_check(complete(record))
    # The by-name searches leave a too-broad query to ADS's object search; nothing stands for ADS's own.
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == [
        "ads TIC 164767175: too_broad (5 papers; nothing stands for it)"
    ]
    assert len(check.evidence["too_broad"]) == 7 and check.evidence["hits"] == []


def test_a_failed_source_leaves_the_search_incomplete(slept):
    web = Web(
        hits={("arxiv", "HIP 8152"): [AKANA]},
        status={("openalex", "HIP 8152"): 429, "zenodo": 503},
    )
    record = search(web)
    openalex, zenodo = record["sources"]["openalex"], record["sources"]["zenodo"]
    # OpenAlex's daily cap won't lift within a retry's wait; a server error is tried three times.
    assert openalex["HIP 8152"] == {
        "status": "error",
        "hits": [],
        "total": None,
        "error": "OpenAlex: HTTP 429",
    }
    assert openalex["TIC 164767175"]["status"] == "ok"
    assert zenodo["HIP 8152"]["status"] == "error" and "HTTP 503" in zenodo["HIP 8152"]["error"]
    assert sum(c["service"] == "zenodo" for c in web.calls) == 6
    # arXiv's one request per three seconds, beside the retries' waits.
    assert slept.count(CFG["arxiv_pause_s"]) == 2
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.INCONCLUSIVE
    assert [i.split(":")[0] for i in check.evidence["incomplete"]] == [
        "openalex HIP 8152",
        "zenodo TIC 164767175",
        "zenodo HIP 8152",
    ]
    assert check.reason.startswith("incomplete: 3 of ")
    # What was found is still listed.
    assert [h["arxiv"] for h in check.evidence["hits"]] == ["2306.16587"]

    # arXiv now and then answers an empty page short of its total; that is not the end of the hits.
    short = Web()
    short.arxiv = lambda name, params: atom([], 3)
    arxiv = search(short)["sources"]["arxiv"]["HIP 8152"]
    assert arxiv["status"] == "error" and "empty" in arxiv["error"]

    whole = complete(search(Web()))
    assert literature.literature_check(whole).outcome == Outcome.PASS
    for broken in (
        {"simbad": {"status": "error", "names": [], "error": "SIMBAD: HTTP 500"}},
        {"exofop": {**whole["exofop"], "status": "error"}},
        {"sources": {k: v for k, v in whole["sources"].items() if k != "openalex"}},
    ):
        check = literature.literature_check({**whole, **broken})
        assert check.outcome == Outcome.INCONCLUSIVE, broken
    # Nothing searched is never complete.
    empty = literature.literature_check({})
    assert empty.outcome == Outcome.INCONCLUSIVE
    assert empty.evidence["incomplete"] == [
        "SIMBAD: not_searched",
        "arxiv: not_searched",
        "openalex: not_searched",
        "zenodo: not_searched",
        "ads: not_searched",
        "ExoFOP: not_searched",
    ]


def test_ads_without_a_token_is_not_searched():
    web = Web(hits={("ads", "TIC 164767175"): [AKANA]})
    record = search(web, token=None)
    assert record["sources"]["ads"] == {
        "TIC 164767175": {
            "status": "not_searched",
            "hits": [],
            "total": None,
            "error": "no ADS_API_TOKEN at run time",
        }
    }
    assert not any(c["service"] in ("objects", "ads") for c in web.calls)
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == [
        "ads TIC 164767175: not_searched (no ADS_API_TOKEN at run time)"
    ]
    # With the token, ADS's object service translates the object query once, and the search pages with the query it
    # returned. Both carry the token as a bearer header.
    record = search(web)
    translate, ads = [c for c in web.calls if c["service"] in ("objects", "ads")]
    assert translate["service"] == "objects"
    assert translate["body"] == {"query": ['object:"TIC 164767175"']}
    assert ads["service"] == "ads" and ads["params"]["q"] == QUERY
    for call in (translate, ads):
        assert call["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    result = record["sources"]["ads"]["TIC 164767175"]
    assert result["query"] == QUERY and result["resolved"] == {"simbad": True, "ned": False}
    assert result["note"] is None
    assert [h["arxiv"] for h in result["hits"]] == ["2306.16587"]
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.PASS and check.evidence["notes"] == []


def test_a_star_no_catalog_resolves_is_searched_by_its_phrase():
    # Neither SIMBAD nor NED knows the star (as TIC 295140687 on the second list): both ids come back "0".
    web = Web(names={}, hits={("ads", "TIC 164767175"): [AKANA]})
    record = search(web)
    result = record["sources"]["ads"]["TIC 164767175"]
    assert result["query"] == QUERY.replace(SIMBID, "0")
    assert result["resolved"] == {"simbad": False, "ned": False}
    assert result["note"] == (
        'No catalog resolved the star, so ADS searched only the phrase "TIC 164767175" in the abstracts, titles '
        "and keywords of its astronomy collection."
    )
    # The search still runs and its hits count; the by-name searches cover the star's other names (decision 0027).
    # SIMBAD answered, without the star.
    check = literature.literature_check({"simbad": literature.simbad_record(TIC, web), **record})
    assert check.outcome == Outcome.PASS
    assert check.evidence["hits"][0]["found_by"] == ["ads TIC 164767175"]
    # The note sits in the evidence, beside a reason that reads as any complete search's.
    assert check.evidence["notes"] == [result["note"]]
    assert check.reason == "complete: 1 hits to screen"


def test_an_unresolved_star_leaves_a_too_broad_name_uncovered():
    cfg = {**CFG, "max_hits": 3}
    many = [paper(f"Paper {i}", f"10.1/{i}", f"2601.{i:05d}") for i in range(5)]
    hits = {("openalex", "HIP 8152"): many}
    # Resolved through SIMBAD, ADS's object search stands for the name OpenAlex found too much for.
    resolved = search(Web(hits=hits), cfg=cfg)
    assert literature.literature_check(complete(resolved)).outcome == Outcome.PASS
    # Unresolved, ADS searched the TIC's phrase alone, which does not cover the name.
    web = Web(names={}, hits=hits)
    record = search(web, cfg=cfg)
    check = literature.literature_check({"simbad": literature.simbad_record(TIC, web), **record})
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == [
        "openalex HIP 8152: too_broad (5 hits; ADS searched only the TIC's phrase, so nothing stands for it)"
    ]


def ads_lookup_failed(name, body):
    """ADS's object service when its own SIMBAD and NED lookups failed: "0" for both, as for a star neither holds."""
    query = f'((=abs:"{name}" OR simbid:"0" OR nedid:"0") database:astronomy)'
    return json.dumps({"query": query}).encode()


def test_ads_not_resolving_a_star_simbad_knows_is_ads_failing():
    web = Web(hits={("ads", "TIC 164767175"): [AKANA]})
    web.objects = ads_lookup_failed
    record = search(web)
    error = "ADS objects: SIMBAD knows TIC 164767175 but ADS's object service did not resolve it"
    assert record["sources"]["ads"]["TIC 164767175"] == {
        "status": "error",
        "hits": [],
        "total": None,
        "error": error,
    }
    # No search on the phrase alone.
    assert [c["service"] for c in web.calls if c["service"] in ("objects", "ads")] == ["objects"]
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == [f"ads TIC 164767175: error ({error})"]

    # With SIMBAD's own lookup failed, nothing says SIMBAD knows the star: the phrase is searched, and SIMBAD's error
    # already leaves the search incomplete.
    failed = Web(status={"simbad": 400}, hits={("ads", "TIC 164767175"): [AKANA]})
    failed.objects = ads_lookup_failed
    record = search(failed)
    ads = record["sources"]["ads"]["TIC 164767175"]
    assert ads["status"] == "ok" and ads["note"] and len(ads["hits"]) == 1
    check = literature.literature_check({"simbad": literature.simbad_record(TIC, failed), **record})
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == ["SIMBAD: error (SIMBAD: HTTP 400)"]


def test_a_failed_translation_is_ads_failing():
    # The object service answers its own errors with a 200 and no query (adsabs-dev-api, openapi/services/objects.yaml).
    no_query = Web()
    no_query.objects = lambda name, body: json.dumps(
        {"Error": "Unable to get results!", "Error Info": f"Bearer {TOKEN}"}
    ).encode()
    for web, error in (
        (Web(status={"objects": 400}), "ADS objects: HTTP 400"),
        (no_query, "ADS objects: no query in the answer"),
    ):
        record = search(web)
        assert record["sources"]["ads"]["TIC 164767175"] == {
            "status": "error",
            "hits": [],
            "total": None,
            "error": error,
        }
        # Asked once, not retried, and the search never runs without a query.
        assert [c["service"] for c in web.calls if c["service"] in ("objects", "ads")] == [
            "objects"
        ]
        check = literature.literature_check(complete(record))
        assert check.outcome == Outcome.INCONCLUSIVE
        assert check.evidence["incomplete"] == [f"ads TIC 164767175: error ({error})"]
        text = json.dumps([record, check.to_dict()])
        assert TOKEN not in text and "Bearer" not in text


class EchoingAds(Web):
    """An ADS service, the object service's POST or the search's GET, that answers with the request's headers in its
    body, or fails naming them."""

    def __init__(self, service, mode):
        super().__init__()
        self.service = service
        self.mode = mode

    def answer(self, service, kind, sent, headers):
        if service != self.service:
            return super().answer(service, kind, sent, headers)
        if self.mode == "raise":
            raise requests.ConnectionError(f"refused with {headers}")
        body = json.dumps({"error": "unauthorized", "headers": headers}).encode()
        return FakeResponse(401 if self.mode == "401" else 200, body)


@pytest.mark.parametrize("service", ["objects", "ads"])
@pytest.mark.parametrize("mode", ["401", "raise", "200"])
def test_the_token_never_reaches_the_record(service, mode):
    record = search(EchoingAds(service, mode))
    ads = record["sources"]["ads"]["TIC 164767175"]
    assert ads["status"] == "error"
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.INCONCLUSIVE
    text = json.dumps([record, check.to_dict()])
    assert TOKEN not in text and "Bearer" not in text


def test_exofop_record_keeps_comments_and_imaging():
    exofop = search(Web())["exofop"]
    assert exofop["status"] == "ok" and exofop["error"] is None
    assert exofop["comments"] == [
        {"object": "TOI 266.01", "comment": "a note on TOI 266.01"},
        {"object": "TIC 164767175.03", "comment": "single transit"},
    ]
    assert exofop["imaging"] == EXOFOP["imaging"]
    assert exofop["files"] == ["TIC164767175-01_PEST.zip", "TOI266I-dc20191015-562.dat"]
    assert exofop["tois"] == EXOFOP["tois"] and exofop["ctois"] == EXOFOP["ctois"]
    assert exofop["confirmed_planets"] == "HIP 8152 b, HIP 8152 c"
    # The periods live in the planet parameters, not the TOI and CTOI entries; the "passed" bar compares them
    # (decision 0028).
    assert exofop["planets"] == [
        {
            "provenance": "Confirmed Planets (Exoplanet Archive)",
            "name": "HIP 8152 b",
            "toi": None,
            "period": 10.751014,
            "epoch_bjd": 2458393.0855,
            "duration_hours": pytest.approx(2.9954278382616),
            "disposition": None,
        },
        {
            "provenance": "Planet Parameters (User uploaded)",
            "name": "TIC 164767175.01",
            "toi": "TOI 266.01",
            "period": None,
            "epoch_bjd": 2459176.2933,
            "duration_hours": 8.2,
            "disposition": "PC",
        },
    ]
    assert set(exofop) == {
        "status",
        "tois",
        "ctois",
        "comments",
        "imaging",
        "files",
        "confirmed_planets",
        "planets",
        "error",
    }
    failed = search(Web(status={"exofop": 404}))["exofop"]
    assert failed["status"] == "error" and failed["error"] == "ExoFOP: HTTP 404"
    assert failed["tois"] == [] and failed["imaging"] == [] and failed["planets"] == []
    # A page without the planet parameters is read as a failure, never as "nothing at the period".
    changed = {k: v for k, v in EXOFOP.items() if k != "planet_parameters"}
    web = Web()
    web.exofop = lambda name, params: json.dumps(changed).encode()
    assert search(web)["exofop"]["status"] == "error"


def test_hits_are_deduplicated_by_doi_arxiv_id_or_title():
    preprint = paper("The TESS-Keck Survey. XVI. Mass Measurements", arxiv="2306.16587")
    journal = paper("The TESS-Keck Survey XVI: mass measurements", doi="10.0000/tks16")
    both = paper("TKS XVI", doi="10.0000/TKS16", arxiv="2306.16587")
    arxiv_doi = paper("Another title", doi="10.48550/arXiv.2306.16587")
    other = paper("A different planet", doi="10.0000/other", arxiv="2401.00001")
    web = Web(
        hits={
            ("arxiv", "HIP 8152"): [preprint, other],
            ("openalex", "TIC 164767175"): [journal, arxiv_doi],
            ("ads", "TIC 164767175"): [both],
        }
    )
    check = literature.literature_check(complete(search(web)))
    assert check.outcome == Outcome.PASS and check.reason == "complete: 2 hits to screen"
    first, second = check.evidence["hits"]
    assert first["title"] == preprint["title"]
    assert first["arxiv"] == "2306.16587" and first["doi"] == "10.0000/tks16"
    assert first["found_by"] == ["ads TIC 164767175", "arxiv HIP 8152", "openalex TIC 164767175"]
    assert second["title"] == "A different planet" and second["found_by"] == ["arxiv HIP 8152"]


# The published record (decision 0038): ADS's titles and ExoFOP's comments, file names, observers and notes out.

ADS_DOI = paper("Validation of the new Hipparcos reduction", doi="10.1051/0004-6361:20078357")
ADS_ARXIV = paper("A preprint only ADS titled here", arxiv="2410.00002")
ADS_BARE = paper("A catalogue only ADS titles here")
OBSERVED = {
    **EXOFOP["imaging"][0],
    "imuser": "observer1",
    "inotes": " PI: Someone; contact: Someone",
    # A field no record has shown: dropped by the allowlist, never published unread.
    "ireducer": "observer3",
}
# A CTOI row as ExoFOP serves it, with its submitter (cuser) and a user field no record has shown.
SUBMITTED = {**EXOFOP["ctois"][0], "cuser": "submitter1", "cemail": "someone@example.org"}
# OpenAlex's titles by DOI: one work titled, one without a title.
TITLES = {
    "10.1051/0004-6361:20078357": "Validation of the new Hipparcos reduction",
    "10.48550/arxiv.2410.00002": None,
}


def full_record(web: Web | None = None) -> dict:
    """A literature record as `vetting literature` writes it, with ADS's hits beside arXiv's."""
    web = web or Web(
        hits={
            ("arxiv", "HIP 8152"): [AKANA],
            ("ads", "TIC 164767175"): [AKANA, ADS_DOI, ADS_ARXIV, ADS_BARE],
        },
        titles=TITLES,
    )
    page = {**EXOFOP, "imaging": [OBSERVED], "ctois": [SUBMITTED]}
    web.exofop = lambda name, params: json.dumps(page).encode()
    found = complete(search(web))
    check = literature.literature_check(found).to_dict()
    return {"signal": {"name": "1-1", "tic": TIC}, "vetting_run": "v", "search": found, **check}


def test_trim_keeps_every_identifier_and_takes_titles_only_from_open_sources():
    record = full_record()
    web = Web(titles=TITLES)
    # Akana's arXiv hit gives its title; the bare bibcode has nothing to look up by.
    dois = literature.to_look_up(record)
    assert dois == ["10.1051/0004-6361:20078357", "10.48550/arxiv.2410.00002"]
    lookups = {doi: literature.openalex_title(web, doi) for doi in dois}
    before = json.dumps(record, sort_keys=True)
    out = literature.trim(record, "f" * 64, lookups, "titles-run")
    assert json.dumps(record, sort_keys=True) == before

    papers = {p["arxiv"] or p["doi"] or p["ids"][0]: p for p in out["evidence"]["hits"]}
    akana = papers[AKANA["arxiv"]]
    assert (akana["title"], akana["title_source"]) == (AKANA["title"], "arxiv")
    found = papers[ADS_DOI["doi"]]
    assert (found["title"], found["title_source"]) == (TITLES[ADS_DOI["doi"]], "openalex_doi")
    for p in (papers[ADS_ARXIV["arxiv"]], papers["2023AJ....166..153A"]):
        assert p["title"] is None and p["title_source"] is None
    # Identifiers and who found each paper stay.
    for paper_in, paper_out in zip(
        record["evidence"]["hits"], out["evidence"]["hits"], strict=True
    ):
        for key in ("doi", "arxiv", "ids", "found_by"):
            assert paper_out[key] == paper_in[key]
    text = json.dumps(out)
    assert ADS_ARXIV["title"] not in text and ADS_BARE["title"] not in text

    # Every search keeps its query, total and status; ADS's hits keep their bibcodes, DOIs and arXiv ids only.
    [ads_in] = record["search"]["sources"]["ads"].values()
    [ads_out] = out["search"]["sources"]["ads"].values()
    assert ads_out["hits"] == [{k: v for k, v in h.items() if k != "title"} for h in ads_in["hits"]]
    assert {k: v for k, v in ads_out.items() if k != "hits"} == {
        k: v for k, v in ads_in.items() if k != "hits"
    }
    for source in literature.OPEN_SOURCES:
        assert out["search"]["sources"][source] == record["search"]["sources"][source]
    for key in ("outcome", "reason", "signal", "vetting_run"):
        assert out[key] == record[key]

    # ExoFOP: the rows stay with only their allowlisted fields: no comment text, file names, submitters, observers,
    # notes, or a field no record has shown.
    exofop = out["search"]["exofop"]
    assert "comments" not in exofop and "files" not in exofop
    assert exofop["tois"] == [{k: v for k, v in t.items() if k != "notes"} for t in EXOFOP["tois"]]
    assert exofop["ctois"] == [{"ctoi": "TIC 164767175.03", "cdisp": "PC"}]
    assert exofop["imaging"] == EXOFOP["imaging"]
    assert exofop["planets"] == record["search"]["exofop"]["planets"]
    assert exofop["confirmed_planets"] == "HIP 8152 b, HIP 8152 c"
    gone = (
        "a note on TOI 266.01",
        "single transit",
        "observer1",
        "observer3",
        "submitter1",
        "someone@",
        "PEST.zip",
    )
    for word in (*gone, "contact"):
        assert word not in text
    assert out["trim"] == {
        "decision": "0038",
        "source_sha256": "f" * 64,
        "titles_run": "titles-run",
        "dropped": [
            *literature.DROPPED,
            "fields outside literature.EXOFOP_FIELDS: search.exofop.ctois[].cemail, search.exofop.ctois[].cuser, "
            "search.exofop.ctois[].paper, search.exofop.imaging[].ireducer",
        ],
    }

    # A lookup that failed, or one never made, leaves the title unknown: refused, not left blank.
    failed = {**lookups, ADS_DOI["doi"]: {**lookups[ADS_DOI["doi"]], "status": "error"}}
    with pytest.raises(literature.TrimError, match="failed to look up"):
        literature.trim(record, "f" * 64, failed, "titles-run")
    with pytest.raises(literature.TrimError, match="did not look up"):
        literature.trim(record, "f" * 64, {}, "titles-run")


def test_openalex_title_is_looked_up_by_doi():
    web = Web(
        titles={"10.1/a(b)": "A  paper\n title", "10.1/none": None},
        status={("lookup", "10.1/down"): 429},
    )
    assert literature.openalex_title(web, "10.1/a(b)") == {
        "status": "ok",
        "title": "A paper title",
        "id": "https://openalex.org/W9",
        "error": None,
    }
    assert literature.openalex_title(web, "10.1/none")["title"] is None
    assert literature.openalex_title(web, "10.1/gone") == {
        "status": "not_found",
        "title": None,
        "id": None,
        "error": None,
    }
    assert literature.openalex_title(web, "10.1/down") == {
        "status": "error",
        "title": None,
        "id": None,
        "error": "OpenAlex: HTTP 429",
    }
    assert [c["name"] for c in web.calls] == ["10.1/a(b)", "10.1/none", "10.1/gone", "10.1/down"]


# `vetting literature`


def vetting_run(tmp_path, monkeypatch, *extra) -> tuple:
    # The control's TIC radius fails its radius check, so by default only TIC 1's two signals are searched.
    monkeypatch.setattr(tv, "CONTROL", {**tv.CONTROL, "rad": 10.0})
    signals = [*tv.SIGNALS, {"name": "1-2", "tic": 1, **tv.SIGNAL, "kind": "candidate"}]
    argv, _ = tv.setup(tmp_path, monkeypatch, signals=signals, fit=tv.fake_fit)
    assert main([*argv, *extra]) == 0
    [run] = (tmp_path / "data" / "runs").glob("*-vetting-run-*")
    return run, [
        "vetting",
        "literature",
        *("--run", str(run)),
        *("--criteria-search", str(tv.SEARCH)),
        *("--criteria-vet", str(tv.VET3)),
    ]


def literature_runs(tmp_path) -> list:
    return sorted((tmp_path / "data" / "runs").glob("*-vetting-literature-*"))


def online(monkeypatch, web: Web) -> Web:
    monkeypatch.setattr(vetting.requests, "Session", lambda: web)
    return web


# TIC 1 in SIMBAD under one more searched name; TIC 2 not at all.
NAMES = {1: ["TIC 1", "HD  1", "BD-19   302"]}


def test_vetting_literature_writes_one_record_per_signal(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    web = online(monkeypatch, Web(names=NAMES, hits={("arxiv", "HD 1"): [AKANA]}))
    assert main(argv) == 0
    [out] = literature_runs(tmp_path)
    assert sorted(p.name for p in (out / "signals").iterdir()) == ["1-1", "1-2"]
    # One star at a time, each searched once for all its signals.
    assert [c["name"] for c in web.calls if c["service"] == "simbad"] == ["TIC 1"]
    record = json.loads((out / "signals" / "1-1" / "literature.json").read_text())
    assert record["signal"] == {"name": "1-1", "tic": 1} and record["vetting_run"] == run.name
    assert record["search"]["simbad"] == {"status": "ok", "names": NAMES[1], "error": None}
    # The Gaia DR3 name from the targets row, which SIMBAD lacks here.
    assert record["search"]["names"] == ["TIC 1", "HD 1", "Gaia DR3 101"]
    assert record["check"] == "literature" and record["outcome"] == "inconclusive"
    assert record["evidence"]["incomplete"] == [
        "ads TIC 1: not_searched (no ADS_API_TOKEN at run time)"
    ]
    assert [h["arxiv"] for h in record["evidence"]["hits"]] == ["2306.16587"]
    assert record["search"]["exofop"]["status"] == "ok"
    twin = json.loads((out / "signals" / "1-2" / "literature.json").read_text())
    assert twin["search"] == record["search"]

    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["vetting_run"] == run.name and provenance["ads_searched"] is False
    assert provenance["resumed_from"] is None
    assert provenance["criteria"][1]["sha256"] == load_criteria(tv.VET3).sha256
    checks = run / "signals" / "1-1" / "checks.json"
    assert provenance["inputs"]["checks_1-1"]["sha256"] == sha256_file(checks)
    assert provenance["summary"]["signals"]["1-1"] == {
        "tic": 1,
        "outcome": "inconclusive",
        "reason": record["reason"],
        "sha256": sha256_file(out / "signals" / "1-1" / "literature.json"),
    }

    # Named, a signal that failed a check is searched too; TIC 2 is not in SIMBAD, so its row names it.
    assert main([*argv, "--signals", "TOI-9.01"]) == 0
    [named] = [p for p in literature_runs(tmp_path) if p != out]
    control = json.loads((named / "signals" / "TOI-9.01" / "literature.json").read_text())
    assert control["search"]["simbad"]["names"] == [] and control["search"]["names"] == ["TIC 2"]


def test_resume_fills_only_what_the_earlier_run_left_incomplete(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    online(
        monkeypatch,
        Web(names=NAMES, hits={("arxiv", "HD 1"): [AKANA]}, status={("openalex", "HD 1"): 429}),
    )
    assert main(argv) == 0
    [first] = literature_runs(tmp_path)

    monkeypatch.setenv("ADS_API_TOKEN", TOKEN)
    web = online(monkeypatch, Web(names=NAMES, hits={("ads", "TIC 1"): [AKANA]}))
    assert main([*argv, "--resume-from", str(first)]) == 0
    [second] = [p for p in literature_runs(tmp_path) if p != first]
    # SIMBAD and ExoFOP are read live; of the searches, only those the first run left incomplete.
    assert {(c["service"], c["name"]) for c in web.calls} == {
        ("simbad", "TIC 1"),
        ("exofop", "TIC 1"),
        ("openalex", "HD 1"),
        ("objects", "TIC 1"),
        ("ads", "TIC 1"),
    }
    record = json.loads((second / "signals" / "1-1" / "literature.json").read_text())
    sources = record["search"]["sources"]
    assert sources["arxiv"]["HD 1"]["from_run"] == first.name
    assert (
        "from_run" not in sources["openalex"]["HD 1"] and "from_run" not in sources["ads"]["TIC 1"]
    )
    assert record["outcome"] == "pass" and record["reason"] == "complete: 1 hits to screen"
    assert record["evidence"]["hits"][0]["found_by"] == ["ads TIC 1", "arxiv HD 1"]
    provenance = json.loads((second / "provenance.json").read_text())
    assert provenance["resumed_from"] == first.name and provenance["ads_searched"] is True
    earlier = first / "signals" / "1-1" / "literature.json"
    assert provenance["inputs"]["resume_1-1"]["sha256"] == sha256_file(earlier)
    # The token reaches no file of the run, nor the argv it records.
    for path in second.rglob("*"):
        if path.is_file():
            assert TOKEN not in path.read_text()

    # A record changed since its run wrote it is not resumed from.
    (first / "signals" / "1-1").chmod(0o755)
    earlier.chmod(0o644)
    earlier.write_text(earlier.read_text().replace('"ok"', '"OK"', 1))
    with pytest.raises(SystemExit, match="is not the file"):
        main([*argv, "--resume-from", str(first)])


def test_resume_asks_ads_again_after_its_lookup_failed(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    monkeypatch.setenv("ADS_API_TOKEN", TOKEN)
    # SIMBAD knows TIC 1, and ADS's object service did not resolve it.
    failed = Web(names=NAMES, hits={("ads", "TIC 1"): [AKANA]})
    failed.objects = ads_lookup_failed
    online(monkeypatch, failed)
    assert main(argv) == 0
    [first] = literature_runs(tmp_path)
    record = json.loads((first / "signals" / "1-1" / "literature.json").read_text())
    assert record["search"]["sources"]["ads"]["TIC 1"]["status"] == "error"
    assert record["outcome"] == "inconclusive"

    web = online(monkeypatch, Web(names=NAMES, hits={("ads", "TIC 1"): [AKANA]}))
    assert main([*argv, "--resume-from", str(first)]) == 0
    [second] = [p for p in literature_runs(tmp_path) if p != first]
    # Of the searches, only ADS's is made again.
    assert {(c["service"], c["name"]) for c in web.calls} == {
        ("simbad", "TIC 1"),
        ("exofop", "TIC 1"),
        ("objects", "TIC 1"),
        ("ads", "TIC 1"),
    }
    record = json.loads((second / "signals" / "1-1" / "literature.json").read_text())
    ads = record["search"]["sources"]["ads"]["TIC 1"]
    assert ads["status"] == "ok" and ads["resolved"]["simbad"] and "from_run" not in ads
    assert record["outcome"] == "pass"


def test_resume_asks_ads_again_once_simbad_knows_the_star(tmp_path, monkeypatch):
    run, argv = vetting_run(tmp_path, monkeypatch)
    monkeypatch.setenv("ADS_API_TOKEN", TOKEN)
    # A SIMBAD outage: our SIMBAD answer fails, and ADS's own lookup gives "0", so ADS searches the phrase alone.
    outage = Web(names=NAMES, status={"simbad": 400}, hits={("ads", "TIC 1"): [AKANA]})
    outage.objects = ads_lookup_failed
    online(monkeypatch, outage)
    assert main(argv) == 0
    [first] = literature_runs(tmp_path)
    record = json.loads((first / "signals" / "1-1" / "literature.json").read_text())
    ads = record["search"]["sources"]["ads"]["TIC 1"]
    assert ads["status"] == "ok" and ads["note"] and record["outcome"] == "inconclusive"

    def resumed(web: Web) -> dict:
        before = set(literature_runs(tmp_path))
        online(monkeypatch, web)
        assert main([*argv, "--resume-from", str(first)]) == 0
        [path] = set(literature_runs(tmp_path)) - before
        return json.loads((path / "signals" / "1-1" / "literature.json").read_text())

    # SIMBAD names the star now, so the phrase-only answer is not kept: ADS is asked again, and a "0" again is ADS
    # failing.
    still = Web(names=NAMES, hits={("ads", "TIC 1"): [AKANA]})
    still.objects = ads_lookup_failed
    record = resumed(still)
    called = {(c["service"], c["name"]) for c in still.calls}
    assert ("objects", "TIC 1") in called and ("ads", "TIC 1") not in called
    assert record["search"]["sources"]["ads"]["TIC 1"] == {
        "status": "error",
        "hits": [],
        "total": None,
        "error": "ADS objects: SIMBAD knows TIC 1 but ADS's object service did not resolve it",
    }
    assert record["outcome"] == "inconclusive"
    # With ADS's lookup working, the search is resolved through SIMBAD and passes.
    record = resumed(Web(names=NAMES, hits={("ads", "TIC 1"): [AKANA]}))
    ads = record["search"]["sources"]["ads"]["TIC 1"]
    assert ads["resolved"]["simbad"] and "from_run" not in ads and record["outcome"] == "pass"


def other_vet_criteria(tmp_path, run) -> list[str]:
    path = tmp_path / "vet-other.toml"
    path.write_text(tv.VET3.read_text() + "# not the file the vetting run used\n")
    return ["--criteria-vet", str(path)]


@pytest.mark.parametrize(
    "extra, message",
    [
        (other_vet_criteria, "is not the criteria/vet-v3.toml that"),
        (
            lambda tmp_path, run: ["--criteria-vet", "criteria/vet-v2.toml"],
            "has no \\[literature\\]",
        ),
        (lambda tmp_path, run: ["--signals", "9-9"], "vetted no 9-9"),
        (lambda tmp_path, run: ["--production"], "not a production vetting run"),
        (lambda tmp_path, run: ["--resume-from", str(run)], "not a finished literature run"),
    ],
)
def test_literature_refuses_what_it_cannot_stand_behind(tmp_path, monkeypatch, extra, message):
    run, argv = vetting_run(tmp_path, monkeypatch)
    online(monkeypatch, Web(names=NAMES))
    with pytest.raises(SystemExit, match=message):
        main([*argv, *extra(tmp_path, run)])
    assert literature_runs(tmp_path) == []


def test_literature_refuses_an_evidence_only_run(tmp_path, monkeypatch):
    _, argv = vetting_run(tmp_path, monkeypatch, "--include-suspect")
    online(monkeypatch, Web(names=NAMES))
    with pytest.raises(SystemExit, match="evidence-only"):
        main(argv)
    assert literature_runs(tmp_path) == []


def test_vetting_titles_looks_up_only_the_papers_no_open_source_titles(tmp_path, monkeypatch):
    _, argv = vetting_run(tmp_path, monkeypatch)
    monkeypatch.setenv("ADS_API_TOKEN", TOKEN)
    hits = {("arxiv", "HD 1"): [AKANA], ("ads", "TIC 1"): [AKANA, ADS_DOI, ADS_BARE]}
    web = online(monkeypatch, Web(names=NAMES, hits=hits, titles=TITLES))
    assert main(argv) == 0
    [lit] = literature_runs(tmp_path)
    assert main(["vetting", "titles", "--literature", str(lit)]) == 0
    [run] = (tmp_path / "data" / "runs").glob("*-vetting-titles-*")
    # Akana has arXiv's title and the bare bibcode no DOI: one lookup, for both signals on the star.
    assert [c["name"] for c in web.calls if c["service"] == "lookup"] == [ADS_DOI["doi"]]
    titles = json.loads((run / "titles.json").read_text())
    assert titles == {
        "literature_run": lit.name,
        "titles": {
            ADS_DOI["doi"]: {
                "status": "ok",
                "title": TITLES[ADS_DOI["doi"]],
                "id": f"https://openalex.org/W{len(ADS_DOI['doi'])}",
                "error": None,
            }
        },
    }
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["stage"] == "vetting-titles" and provenance["literature_run"] == lit.name
    for name in ("1-1", "1-2"):
        record = lit / "signals" / name / "literature.json"
        assert provenance["inputs"][f"literature_{name}"]["sha256"] == sha256_file(record)
    assert provenance["summary"]["titles_sha256"] == sha256_file(run / "titles.json")
    assert provenance["summary"]["error"] == 0 and provenance["summary"]["titled"] == 1
    # A literature record changed since its run wrote it is refused before any lookup.
    record = lit / "signals" / "1-1" / "literature.json"
    record.chmod(0o644)
    record.write_text(record.read_text().replace("TIC 1", "TIC 7"))
    with pytest.raises(SystemExit, match="is not the file it wrote"):
        main(["vetting", "titles", "--literature", str(lit)])


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("ADS_API_TOKEN"), reason="ADS needs ADS_API_TOKEN")
def test_hip_8152_finds_akana_murphy_2023():
    session = requests.Session()
    simbad = literature.simbad_record(TIC, session)
    names = literature.searchable(simbad["names"], {"tic": TIC}, CFG["forms"])
    assert "HIP 8152" in names
    record = literature.search_all(
        TIC, names, session, os.environ["ADS_API_TOKEN"], CFG, simbad=simbad
    )
    ads = record["sources"]["ads"]["TIC 164767175"]
    # ADS itself must find Akana Murphy et al. 2023, AJ 166, 153 (TOI-266's planets as HIP 8152 b and c): arXiv's search
    # by "HIP 8152" never finds it, and ADS's search failed for every star until its HTTP 400 came to light on
    # 2026-10-19.
    assert ads["status"] == "ok", ads["error"]
    assert ads["resolved"]["simbad"]
    assert any(h["id"] == "2023AJ....166..153A" for h in ads["hits"])
