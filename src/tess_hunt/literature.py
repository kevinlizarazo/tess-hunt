"""Has anyone written about this star? Triage searches by TIC (docs/design.md, section 4.1); vetting searches by every
name papers use, NASA ADS's object search and ExoFOP's target page (M3 design, section 4.6; decision 0027). Hits are
evidence for the maintainer to read, not an outcome."""

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from functools import partial

import numpy as np
import requests

from tess_hunt.checks import CheckResult, inconclusive, passed
from tess_hunt.retry import retry

ZENODO = "https://zenodo.org/api/records"
ARXIV = "https://export.arxiv.org/api/query"
OPENALEX = "https://api.openalex.org/works"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
ADS = "https://api.adsabs.harvard.edu/v1/search/query"
ADS_OBJECTS = "https://api.adsabs.harvard.edu/v1/objects/query"
EXOFOP_TARGET = "https://exofop.ipac.caltech.edu/tess/target.php"
ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
ARXIV_ATOM = "{http://arxiv.org/schemas/atom}"
ARXIV_DOI = "10.48550/arxiv."
SOURCES = ("arxiv", "openalex", "zenodo", "ads")
# Searches that answered, which a resumed run keeps. A by-name search that is too broad is left to ADS's object
# search; ADS's own too-broad answer has nothing standing for it, so literature_check counts it as incomplete.
ANSWERED = ("ok", "too_broad")
# The most each service serves in one page without a key (Zenodo refuses more than 25).
PAGE = {"arxiv": 2000, "openalex": 200, "zenodo": 25, "ads": 2000}
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_S = 10.0
NO_TOKEN = "no ADS_API_TOKEN at run time"


class LiteratureError(RuntimeError):
    """A failed request. Its message names the service and at most a status code, never a request header."""


class TransientError(RuntimeError):
    pass


def _get(session, url: str, params: dict):
    response = session.get(url, timeout=60, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    return response


def _zenodo(session, phrase: str) -> list[dict]:
    hits = _get(session, ZENODO, {"q": phrase, "size": 25}).json()["hits"]["hits"]
    return [{"title": h["metadata"]["title"], "id": f"zenodo:{h['id']}"} for h in hits]


def _arxiv(session, phrase: str) -> list[dict]:
    root = ET.fromstring(
        _get(session, ARXIV, {"search_query": f"all:{phrase}", "max_results": 25}).content
    )
    return [
        {"title": e.findtext(f"{ATOM}title", "").strip(), "id": e.findtext(f"{ATOM}id", "")}
        for e in root.iter(f"{ATOM}entry")
    ]


def _openalex(session, phrase: str) -> list[dict]:
    results = _get(
        session, OPENALEX, {"filter": f"fulltext.search:{phrase}", "per-page": 25}
    ).json()["results"]
    return [{"title": r.get("title") or "", "id": r["id"]} for r in results]


def search(tic: int, session, pause: float = 3.0) -> dict:
    # A quoted "TIC n" phrase: Zenodo found nothing for "TIC4206066" and five records for "TIC 4206066".
    phrase = f'"TIC {int(tic)}"'
    out = {}
    for name, query in (("zenodo", _zenodo), ("arxiv", _arxiv), ("openalex", _openalex)):
        try:
            out[name] = {"status": "ok", "hits": query(session, phrase)}
        except Exception as exc:
            # A service being down leaves the search incomplete, which the record says.
            out[name] = {"status": "error", "hits": [], "error": f"{type(exc).__name__}: {exc}"}
        # arXiv asks for one request every three seconds; the others tolerate more.
        time.sleep(pause)
    return out


def _fetch(
    session,
    url: str,
    params: dict | None,
    what: str,
    headers: dict | None = None,
    body: dict | None = None,
):
    def call():
        try:
            response = (
                session.get(url, timeout=60, params=params, headers=headers)
                if body is None
                else session.post(url, timeout=60, json=body, headers=headers)
            )
        except requests.RequestException as exc:
            # The exception's text and its request object can carry the headers, ADS's token among them.
            raise TransientError(type(exc).__name__) from None
        if response.status_code >= 500:
            raise TransientError(f"HTTP {response.status_code}")
        if response.status_code != 200:
            # A 429 is a rate limit or OpenAlex's daily cap, which no retry's wait outlasts.
            raise LiteratureError(f"{what}: HTTP {response.status_code}")
        return response

    return retry(
        call,
        attempts=RETRY_ATTEMPTS,
        backoff=RETRY_BACKOFF_S,
        retry_on=TransientError,
        error=LiteratureError,
        what=what,
        sleep=time.sleep,
    )


def _message(exc: Exception) -> str:
    # Any other exception's text may quote a response body, and a body can echo the request's headers.
    return str(exc) if isinstance(exc, LiteratureError) else type(exc).__name__


def simbad_names(tic: int, session) -> list[str]:
    """Every identifier SIMBAD holds for the star it knows as TIC `tic`, spelled as SIMBAD spells it; [] when SIMBAD
    does not know the star."""
    query = (
        "SELECT id2.id FROM ident AS id1 JOIN ident AS id2 ON id1.oidref = id2.oidref "
        f"WHERE id1.id = 'TIC {int(tic)}'"
    )
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query}
    return [row[0] for row in _fetch(session, SIMBAD_TAP, params, "SIMBAD").json()["data"]]


def simbad_record(tic: int, session) -> dict:
    """simbad_names as the record keeps it: a failure leaves the names to the targets row and the search incomplete."""
    try:
        return {"status": "ok", "names": simbad_names(tic, session), "error": None}
    except Exception as exc:
        return {"status": "error", "names": [], "error": _message(exc)}


def _has_form(name: str, form: str) -> bool:
    return name.startswith((f"{form} ", f"{form}-"))


def searchable(names: list[str], star: Mapping, forms: list[str]) -> list[str]:
    """The names in `forms`, whitespace normalised, with the TIC and Gaia DR3 names from the targets row where SIMBAD
    gave none of that form."""
    found = [" ".join(n.split()) for n in names]
    source_id = star.get("dr3_source_id")
    fallback = {
        "TIC": f"TIC {int(star['tic'])}",
        # An id rounded through a float names another star; None, NaN and pd.NA are missing.
        "Gaia DR3": f"Gaia DR3 {source_id}" if isinstance(source_id, int | np.integer) else None,
    }
    for form, name in fallback.items():
        if name and not any(_has_form(n, form) for n in found):
            found.append(name)
    return list(dict.fromkeys(n for n in found if any(_has_form(n, f) for f in forms)))


def _result(status: str, hits: list[dict] | None = None, total=None, error=None) -> dict:
    return {"status": status, "hits": hits or [], "total": total, "error": error}


def _doi(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value.strip()).lower()


def _hit(title: str | None, id_: str, doi: str | None, arxiv: str | None = None) -> dict:
    doi = _doi(doi)
    if arxiv is None and doi and doi.startswith(ARXIV_DOI):
        arxiv = doi.removeprefix(ARXIV_DOI)
    return {"title": " ".join((title or "").split()), "id": id_, "doi": doi, "arxiv": arxiv}


def _arxiv_id(url: str) -> str | None:
    match = re.search(r"arxiv\.org/abs/(.+?)(v\d+)?$", url)
    return match.group(1) if match else None


def _arxiv_page(session, name: str, page: int, size: int, pause: float) -> tuple[list[dict], int]:
    params = {"search_query": f'all:"{name}"', "start": page * size, "max_results": size}
    try:
        root = ET.fromstring(_fetch(session, ARXIV, params, "arXiv").content)
    finally:
        # arXiv asks for one request every three seconds, failed ones included.
        time.sleep(pause)
    hits = []
    for entry in root.iter(f"{ATOM}entry"):
        url = entry.findtext(f"{ATOM}id", "")
        hits.append(
            _hit(
                entry.findtext(f"{ATOM}title"),
                url,
                entry.findtext(f"{ARXIV_ATOM}doi"),
                _arxiv_id(url),
            )
        )
    return hits, int(root.findtext(f"{OPENSEARCH}totalResults"))


def _openalex_page(session, name: str, page: int, size: int) -> tuple[list[dict], int]:
    params = {"filter": f'fulltext.search:"{name}"', "per-page": size, "page": page + 1}
    data = _fetch(session, OPENALEX, params, "OpenAlex").json()
    return [_hit(r.get("title"), r["id"], r.get("doi")) for r in data["results"]], int(
        data["meta"]["count"]
    )


def _zenodo_page(session, name: str, page: int, size: int) -> tuple[list[dict], int]:
    params = {"q": f'"{name}"', "size": size, "page": page + 1}
    data = _fetch(session, ZENODO, params, "Zenodo").json()["hits"]
    hits = [_hit(h["metadata"]["title"], f"zenodo:{h['id']}", h.get("doi")) for h in data["hits"]]
    return hits, int(data["total"])


def _ads_query(session, star: str, headers: dict) -> str:
    """The query ADS's search takes for `object:"<star>"`, from ADS's object service: its search endpoint has refused
    the `object:` field since at least 2026-10-19 (decision 0027)."""
    body = {"query": [f'object:"{star}"']}
    query = _fetch(session, ADS_OBJECTS, None, "ADS objects", headers, body).json().get("query")
    if not isinstance(query, str):
        # The object service answers its own errors with a 200 and no query.
        raise LiteratureError("ADS objects: no query in the answer")
    return query


def _resolved(query: str, field: str) -> bool:
    # The object service writes "0" for an object the catalog did not resolve.
    match = re.search(rf'\b{field}:"([^"]*)"', query)
    return match is not None and match.group(1) != "0"


def _ads_page(session, query: str, page: int, size: int, headers: dict) -> tuple[list[dict], int]:
    params = {"q": query, "fl": "bibcode,title,doi,identifier", "rows": size, "start": page * size}
    data = _fetch(session, ADS, params, "ADS", headers).json()["response"]
    hits = []
    for doc in data["docs"]:
        ids = doc.get("identifier", [])
        arxiv = next((i.removeprefix("arXiv:") for i in ids if i.startswith("arXiv:")), None)
        title, doi = (doc.get("title") or [""])[0], (doc.get("doi") or [None])[0]
        hits.append(_hit(title, doc["bibcode"], doi, arxiv))
    return hits, int(data["numFound"])


def _paged(page_of: Callable[[int, int], tuple[list[dict], int]], size: int, max_hits: int) -> dict:
    """Every hit, page by page, or too broad at the first page whose total exceeds `max_hits`."""
    hits: list[dict] = []
    page = 0
    while True:
        found, total = page_of(page, size)
        if total > max_hits:
            return _result("too_broad", total=total)
        hits += found
        if len(hits) >= total:
            return _result("ok", hits, total)
        if not found:
            # arXiv now and then answers an empty page short of the total it reported.
            raise LiteratureError(
                f"page {page + 1} came back empty with {len(hits)} of {total} hits"
            )
        page += 1


def _ads(session, star: str, token: str, simbad_knows: bool, size: int, max_hits: int) -> dict:
    """ADS's object search for `star`: translated once, then paged. The record keeps the query ADS searched and which
    catalogs resolved the star."""
    headers = {"Authorization": f"Bearer {token}"}
    query = _ads_query(session, star, headers)
    resolved = {"simbad": _resolved(query, "simbid"), "ned": _resolved(query, "nedid")}
    if simbad_knows and not resolved["simbad"]:
        # The object service also writes "0" when its own SIMBAD lookup fails, and it asks SIMBAD for the identifier
        # SIMBAD just answered us for: a failure, which a resumed run asks again, not a star SIMBAD lacks.
        raise LiteratureError(
            f"ADS objects: SIMBAD knows {star} but ADS's object service did not resolve it"
        )
    # Unresolved, the query is the phrase alone. Its hits still count: the by-name searches cover the other names.
    note = (
        None
        if any(resolved.values())
        else f'No catalog resolved the star, so ADS searched only the phrase "{star}" in the abstracts, titles and '
        "keywords of its astronomy collection."
    )
    found = _paged(partial(_ads_page, session, query, headers=headers), size, max_hits)
    return {**found, "query": query, "resolved": resolved, "note": note}


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _planets(rows: list[dict]) -> list[dict]:
    """ExoFOP's planet parameters, each row under the provenance heading before it (confirmed planets, TOIs, user
    uploads). The TOI and CTOI entries carry no period; these rows do."""
    out, heading = [], None
    for row in rows:
        if row.get("prov"):
            heading = row.get("prov_title") or row["prov"]
            continue
        out.append(
            {
                "provenance": heading,
                "name": row.get("name") or None,
                "toi": row.get("toi") or None,
                "period": _float(row.get("per")),
                "epoch_bjd": _float(row.get("epoch")),
                "duration_hours": _float(row.get("dur")),
                "disposition": row.get("disp") or None,
            }
        )
    return out


def _exofop(tic: int, session) -> dict:
    """ExoFOP's target page, reduced to what speaks to the star's planets: TOIs and CTOIs with their comments, the
    confirmed planets, every planet parameter row with its period, the imaging and the names of the files."""
    try:
        page = _fetch(session, EXOFOP_TARGET, {"id": int(tic), "json": ""}, "ExoFOP").json()
        tois, ctois = page["tois"], page["ctois"]
        comments = [{"object": t["toi"], "comment": t["notes"]} for t in tois if t.get("notes")] + [
            {"object": c["ctoi"], "comment": c["cnotes"]} for c in ctois if c.get("cnotes")
        ]
        return {
            "status": "ok",
            "tois": tois,
            "ctois": ctois,
            "comments": comments,
            "confirmed_planets": page["basic_info"]["confirmed_planets"],
            "planets": _planets(page["planet_parameters"]),
            "imaging": page["imaging"],
            "files": [f["fname"] for f in page["files"]],
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "tois": [],
            "ctois": [],
            "comments": [],
            "confirmed_planets": None,
            "planets": [],
            "imaging": [],
            "files": [],
            "error": _message(exc),
        }


def search_all(
    tic: int,
    names: list[str],
    session,
    ads_token: str | None,
    cfg: Mapping,
    done: Mapping | None = None,
    *,
    simbad: Mapping,
) -> dict:
    """Each name through arXiv, OpenAlex and Zenodo, the star through ADS's object search, and ExoFOP's target page.
    Each search is {status, hits, total, error}, and an answered ADS search also {query, resolved, note}; `done` holds
    searches an earlier run completed, kept as they are. `simbad` is the star's simbad_record: with it, ADS's object
    service failing to resolve a star SIMBAD knows is told apart from a star SIMBAD lacks."""
    done = done or {}

    def search(source: str, name: str, find: Callable[[int, int], dict] | None) -> dict:
        if name in done.get(source, {}):
            return done[source][name]
        if find is None:
            return _result("not_searched", error=NO_TOKEN)
        try:
            return find(min(PAGE[source], cfg["max_hits"]), cfg["max_hits"])
        except Exception as exc:
            # A failed search is recorded, never a negative: the record says the search is incomplete.
            return _result("error", error=_message(exc))

    by_name = {
        "arxiv": partial(_arxiv_page, pause=cfg["arxiv_pause_s"]),
        "openalex": _openalex_page,
        "zenodo": _zenodo_page,
    }
    sources = {
        source: {
            name: search(source, name, partial(_paged, partial(page_of, session, name)))
            for name in names
        }
        for source, page_of in by_name.items()
    }
    # ADS's object service resolves the TIC through SIMBAD and NED, and the search then finds the papers they tag with
    # the star, whatever name the papers use: the TIC stands for all the names.
    star = f"TIC {int(tic)}"
    simbad_knows = simbad["status"] == "ok" and bool(simbad["names"])
    ads = None if ads_token is None else partial(_ads, session, star, ads_token, simbad_knows)
    sources["ads"] = {star: search("ads", star, ads)}
    return {
        "tic": int(tic),
        "names": list(names),
        "sources": sources,
        "exofop": _exofop(tic, session),
    }


def _title_key(title: str) -> str | None:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower())) or None


def _merge(into: dict, other: dict) -> None:
    into["keys"] |= other["keys"]
    into["doi"] = into["doi"] or other["doi"]
    into["arxiv"] = into["arxiv"] or other["arxiv"]
    into["ids"] += other["ids"]
    into["found_by"] += other["found_by"]


def _dedupe(found: list[tuple[str, dict]]) -> list[dict]:
    """One entry per paper: hits that share a DOI, an arXiv id or a title are the same paper."""
    papers: list[dict] = []
    for label, hit in found:
        keys = {
            (kind, value)
            for kind, value in (
                ("doi", hit["doi"]),
                ("arxiv", hit["arxiv"]),
                ("title", _title_key(hit["title"])),
            )
            if value
        }
        same = [p for p in papers if p["keys"] & keys]
        if same:
            paper = same[0]
            for other in same[1:]:
                _merge(paper, other)
                papers.remove(other)
        else:
            paper = {"keys": set(), "title": hit["title"], "doi": None, "arxiv": None}
            paper.update(ids=[], found_by=[])
            papers.append(paper)
        _merge(paper, {**hit, "keys": keys, "ids": [hit["id"]], "found_by": [label]})
    return [
        {
            "title": p["title"],
            "doi": p["doi"],
            "arxiv": p["arxiv"],
            "ids": sorted(set(p["ids"])),
            "found_by": sorted(set(p["found_by"])),
        }
        for p in papers
    ]


def literature_check(record: Mapping) -> CheckResult:
    """Inconclusive while any search failed or was never made (a rate limit is not a negative), or ADS's object search
    was too broad; otherwise the hits, one per paper, for the maintainer and the review to read. It never fails
    (decision 0027)."""
    sources = record.get("sources") or {}
    searches = [("SIMBAD", "SIMBAD", record.get("simbad"))]
    for source in SOURCES:
        made = sources.get(source)
        searches += (
            [(source, f"{source} {name}", r) for name, r in made.items()]
            if made
            else [(source, source, None)]
        )
    searches.append(("ExoFOP", "ExoFOP", record.get("exofop")))
    incomplete = []
    for source, label, r in searches:
        if r is None:
            incomplete.append(f"{label}: not_searched")
        elif source == "ads" and r["status"] == "too_broad":
            incomplete.append(f"{label}: too_broad ({r['total']} papers; nothing stands for it)")
        elif r["status"] not in ANSWERED:
            error = f" ({r['error']})" if r.get("error") else ""
            incomplete.append(f"{label}: {r['status']}{error}")
    answered = [(f"{s} {name}", r) for s in SOURCES for name, r in (sources.get(s) or {}).items()]
    hits = _dedupe([(label, h) for label, r in answered if r["status"] == "ok" for h in r["hits"]])
    evidence = {
        "names": record.get("names", []),
        "hits": hits,
        "too_broad": [
            f"{label}: {r['total']} hits" for label, r in answered if r["status"] == "too_broad"
        ],
        # Beside the reason, not in it: a phrase-only ADS search still counts toward a complete search (decision 0027).
        "notes": [r["note"] for _, r in answered if r.get("note")],
        "incomplete": incomplete,
    }
    if incomplete:
        reason = (
            f"incomplete: {len(incomplete)} of {len(searches)} searches failed or were not made: "
            + "; ".join(incomplete)
        )
        return inconclusive("literature", reason, **evidence)
    return passed("literature", f"complete: {len(hits)} hits to screen", **evidence)
