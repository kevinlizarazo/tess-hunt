import json
import os
import re

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
        {"toi": "TOI 266.01", "disp_tfop": "CP", "notes": "HIP 8152 b/ TOI-266.01"},
        {"toi": "TOI 266.02", "disp_tfop": "CP", "notes": ""},
    ],
    "ctois": [
        {"ctoi": "TIC 164767175.03", "cdisp": "PC", "cnotes": "single transit", "paper": "a paper"}
    ],
    "imaging": [
        {"itel": "Gemini (8 m)", "iinst": "'Alopeke", "itype": "Speckle", "icont": "4.49 @ 0.5"}
    ],
    "spectroscopy": [{"stel": "SMARTS"}],
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
    literature.EXOFOP_TARGET: "exofop",
}
ATOM = (
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" '
    'xmlns:arxiv="http://arxiv.org/schemas/atom">'
)
TOKEN = "ads-token-k3v1n-7f2a"


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
    (service, name), to the HTTP status it answers instead. ADS answers only the bearer `token`."""

    def __init__(self, hits=None, status=None, names=None, token=TOKEN):
        self.hits = hits or {}
        self.status = status or {}
        self.names = {TIC: SIMBAD_IDS} if names is None else names
        self.token = token
        self.calls = []

    def get(self, url, timeout, params=None, headers=None):
        service = SERVICES[url]
        params = dict(params or {})
        name = self.name(service, params)
        self.calls.append(
            {"service": service, "name": name, "params": params, "headers": dict(headers or {})}
        )
        status = self.status.get((service, name), self.status.get(service))
        if status:
            return FakeResponse(status)
        if service == "ads" and (headers or {}).get("Authorization") != f"Bearer {self.token}":
            return FakeResponse(401)
        return FakeResponse(200, getattr(self, service)(name, params))

    @staticmethod
    def name(service: str, params: dict) -> str:
        if service == "simbad":
            return re.search(r"'(TIC \d+)'", params["QUERY"]).group(1)
        if service == "exofop":
            return f"TIC {params['id']}"
        key = {"arxiv": "search_query", "openalex": "filter", "zenodo": "q", "ads": "q"}[service]
        return re.search(r'"(.*)"', params[key]).group(1)

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


@pytest.fixture(autouse=True)
def slept(request, monkeypatch):
    """No unit test waits out arXiv's pause or a retry's backoff; each wait is recorded instead."""
    waits = []
    if not request.node.get_closest_marker("network"):
        monkeypatch.setattr(literature.time, "sleep", waits.append)
    return waits


def search(web, names=("TIC 164767175", "HIP 8152"), token=TOKEN, cfg=CFG, done=None) -> dict:
    return literature.search_all(TIC, list(names), web, token, cfg, done)


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
    assert not any(c["service"] == "ads" for c in web.calls)
    check = literature.literature_check(complete(record))
    assert check.outcome == Outcome.INCONCLUSIVE
    assert check.evidence["incomplete"] == [
        "ads TIC 164767175: not_searched (no ADS_API_TOKEN at run time)"
    ]
    # With the token, ADS's object search goes by the TIC, the token as a bearer header.
    record = search(web)
    [call] = [c for c in web.calls if c["service"] == "ads"]
    assert call["params"]["q"] == 'object:"TIC 164767175"'
    assert call["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert [h["arxiv"] for h in record["sources"]["ads"]["TIC 164767175"]["hits"]] == ["2306.16587"]
    assert literature.literature_check(complete(record)).outcome == Outcome.PASS


class EchoingAds(Web):
    """An ADS that answers with the request's headers in its body, or fails naming them."""

    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def get(self, url, timeout, params=None, headers=None):
        if SERVICES[url] != "ads":
            return super().get(url, timeout, params, headers)
        if self.mode == "raise":
            raise requests.ConnectionError(f"refused with {headers}")
        body = json.dumps({"error": "unauthorized", "headers": headers}).encode()
        return FakeResponse(401 if self.mode == "401" else 200, body)


@pytest.mark.parametrize("mode", ["401", "raise", "200"])
def test_the_token_never_reaches_the_record(mode):
    record = search(EchoingAds(mode))
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
        {"object": "TOI 266.01", "comment": "HIP 8152 b/ TOI-266.01"},
        {"object": "TIC 164767175.03", "comment": "single transit"},
    ]
    assert exofop["imaging"] == EXOFOP["imaging"]
    assert exofop["files"] == ["TIC164767175-01_PEST.zip", "TOI266I-dc20191015-562.dat"]
    assert exofop["tois"] == EXOFOP["tois"] and exofop["ctois"] == EXOFOP["ctois"]
    assert exofop["confirmed_planets"] == "HIP 8152 b, HIP 8152 c"
    assert set(exofop) == {
        "status",
        "tois",
        "ctois",
        "comments",
        "imaging",
        "files",
        "confirmed_planets",
        "error",
    }
    failed = search(Web(status={"exofop": 404}))["exofop"]
    assert failed["status"] == "error" and failed["error"] == "ExoFOP: HTTP 404"
    assert failed["tois"] == [] and failed["imaging"] == []


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


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("ADS_API_TOKEN"), reason="ADS needs ADS_API_TOKEN")
def test_hip_8152_finds_akana_murphy_2023():
    session = requests.Session()
    names = literature.searchable(literature.simbad_names(TIC, session), {"tic": TIC}, CFG["forms"])
    assert "HIP 8152" in names
    record = literature.search_all(TIC, names, session, os.environ["ADS_API_TOKEN"], CFG)
    sources = record["sources"]
    found = [*sources["ads"]["TIC 164767175"]["hits"], *sources["arxiv"]["HIP 8152"]["hits"]]
    # Akana Murphy et al. 2023, AJ 166, 153 (arXiv:2306.16587): TOI-266's planets as HIP 8152 b and c.
    assert any(h["arxiv"] == "2306.16587" or h["id"] == "2023AJ....166..153A" for h in found)
