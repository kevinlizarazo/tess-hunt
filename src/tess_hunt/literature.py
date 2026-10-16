"""Has anyone written about this star? Keyless searches by TIC (docs/design.md, section 4.1). Hits are evidence for the
maintainer to read, not an outcome."""

import time
import xml.etree.ElementTree as ET

ZENODO = "https://zenodo.org/api/records"
ARXIV = "https://export.arxiv.org/api/query"
OPENALEX = "https://api.openalex.org/works"
ATOM = "{http://www.w3.org/2005/Atom}"


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
