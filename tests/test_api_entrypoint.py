"""The deployable entrypoint serves the committed artifacts and nothing else.

The point of these tests is not that the endpoint is important. It is that a
function deployed from this repo must not become a second source of truth for the
table, and must not drag the harness's dependencies into a serverless bundle.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from wsgiref.util import setup_testing_defaults

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("vercel_index", ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api = _load()
_body = api._body
_norm = api._normalise


def _call(path: str, method: str = "GET") -> tuple[str, dict[str, str], bytes]:
    """A request as Vercel delivers it: rewritten to the function, path in the query.

    Calling with PATH_INFO set to the caller's path would test a shape that never
    reaches production. The first deployment 404d on every route precisely because
    the tests asserted against that shape and the rewrite hands over another.
    """
    environ: dict = {"PATH_INFO": "/api/index", "QUERY_STRING": f"path={path}"}
    setup_testing_defaults(environ)
    environ["PATH_INFO"] = "/api/index"
    environ["QUERY_STRING"] = f"path={path}"
    environ["REQUEST_METHOD"] = method
    captured: dict = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(api.app(environ, start_response))
    return captured["status"], captured["headers"], body


def test_results_endpoint_serves_the_committed_file_byte_for_byte():
    status, headers, body = _call("/results.json")
    assert status.startswith("200")
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert body == (ROOT / "results" / "results.json").read_bytes()


def test_it_serves_rather_than_recomputes():
    """A number here that is not in the committed file would be a second table."""
    _, _, body = _call("/results.json")
    assert json.loads(body) == json.loads((ROOT / "results" / "results.json").read_text())


def test_index_and_manifest_and_tables_are_reachable():
    for path in ("/", "/manifest.json", "/tables.md"):
        status, _, body = _call(path)
        assert status.startswith("200"), path
        assert body, path


def test_unknown_path_is_404_and_says_what_it_received():
    status, _, body = _call("/secrets")
    assert status.startswith("404")
    assert b"/secrets" in body, "a 404 that does not echo the path it got is unfixable remotely"
    assert b"/results.json" in body


def test_head_sends_headers_without_a_body():
    status, headers, body = _call("/results.json", method="HEAD")
    assert status.startswith("200")
    assert body == b""
    assert int(headers["Content-Length"]) > 0


def test_writes_are_refused():
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        status, headers, _ = _call("/results.json", method=method)
        assert status.startswith("405"), method
        assert headers["Allow"] == "GET, HEAD"


def test_the_entrypoint_imports_nothing_from_the_harness():
    """It must stay stdlib only, or a serverless bundle pulls torch to serve JSON."""
    source = (ROOT / "api" / "index.py").read_text()
    for banned in ("injection_eval", "torch", "transformers", "sklearn", "datasets"):
        assert f"import {banned}" not in source
        assert f"from {banned}" not in source


def test_nothing_in_the_harness_imports_the_entrypoint():
    for path in (ROOT / "src").rglob("*.py"):
        assert "api.index" not in path.read_text(), path


@pytest.mark.parametrize("name", ["results.json", "manifest.json", "TABLES.md"])
def test_vercel_config_ships_the_files_the_function_reads(name: str):
    config = json.loads((ROOT / "vercel.json").read_text())
    assert config["functions"]["api/index.py"]["includeFiles"] == "results/**"
    assert (ROOT / "results" / name).is_file()


def _raw(path_info: str, query: str) -> tuple[str, bytes]:
    """Call the app with an exact PATH_INFO and QUERY_STRING, bypassing _call."""
    environ: dict = {"PATH_INFO": path_info, "QUERY_STRING": query}
    setup_testing_defaults(environ)
    environ["PATH_INFO"] = path_info
    environ["QUERY_STRING"] = query
    captured: dict = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status

    body = b"".join(api.app(environ, start_response))
    return captured["status"], body


@pytest.mark.parametrize("bare", ["/api/index", "/api/index.py", "/api"])
def test_the_rewrite_destination_alone_serves_the_index(bare: str):
    """A bare hit on the function, with no forwarded path, must not 404."""
    status, body = _raw(bare, "")
    assert status.startswith("200")
    assert b"injection-eval-harness" in body


def test_every_rewrite_in_the_config_forwards_the_original_path():
    """The config and the handler have to agree, or every route 404s in production."""
    config = json.loads((ROOT / "vercel.json").read_text())
    rewrites = config["rewrites"]
    assert rewrites, "no rewrites; requests would never reach the function"
    for rule in rewrites:
        assert rule["destination"] == f"/api/index?path={rule['source']}", rule
        assert _body(_norm(rule["source"]))[0] == 200, rule


def test_every_served_route_has_a_rewrite():
    """A route the handler knows and the config does not is unreachable in production."""
    config = json.loads((ROOT / "vercel.json").read_text())
    sources = {rule["source"] for rule in config["rewrites"]}
    for path in api._ROUTES:
        assert path in sources, f"{path} is served by the handler and not routed to it"


def test_the_page_is_built_and_not_served_by_the_function():
    """`/` is a static file from the build, so the function must not claim it."""
    config = json.loads((ROOT / "vercel.json").read_text())
    assert config["buildCommand"] == "python3 scripts/build_site.py"
    assert config["outputDirectory"] == "public"
    assert "/" not in {rule["source"] for rule in config["rewrites"]}


def test_the_build_script_is_not_excluded_from_the_deployment():
    """.vercelignore excluding what buildCommand runs fails the deploy, not a test."""
    ignored = [
        line.strip()
        for line in (ROOT / ".vercelignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for needed in ("scripts/", "results/", "api/", "public/"):
        assert needed not in ignored, f".vercelignore drops {needed}, which the build needs"


def test_a_path_without_a_leading_slash_is_still_matched():
    status, body = _raw("/api/index", "path=results.json")
    assert status.startswith("200")
    assert body == (ROOT / "results" / "results.json").read_bytes()


@pytest.mark.parametrize(
    "forwarded",
    ["/api/index", "/api/index.py", "/api", "", "/"],
)
def test_the_function_address_forwarded_as_the_path_is_the_index(forwarded: str):
    """`/` and `/api/index` are the one case where caller path and rewrite target
    are the same string, so normalising only the PATH_INFO branch missed both."""
    status, body = _raw("/api/index", f"path={forwarded}")
    assert status.startswith("200"), forwarded
    assert b"injection-eval-harness" in body


def test_a_trailing_slash_does_not_404():
    status, body = _raw("/api/index", "path=/tables.md/")
    assert status.startswith("200")
    assert body == (ROOT / "results" / "TABLES.md").read_bytes()


def test_errors_are_never_cached():
    """A 404 pinned at the edge outlives the deploy that fixes it."""
    environ: dict = {"PATH_INFO": "/api/index", "QUERY_STRING": "path=/nope"}
    setup_testing_defaults(environ)
    environ["PATH_INFO"] = "/api/index"
    environ["QUERY_STRING"] = "path=/nope"
    captured: dict = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    b"".join(api.app(environ, start_response))
    assert captured["status"].startswith("404")
    assert captured["headers"]["Cache-Control"] == "no-store"


def test_success_is_cached():
    _, headers, _ = _call("/results.json")
    assert "s-maxage" in headers["Cache-Control"]


def test_the_page_quotes_only_numbers_that_are_in_results_json():
    """The page is generated, so a figure it shows and results.json does not is a bug."""
    import re
    import subprocess

    subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "build_site.py")],
        check=True,
        capture_output=True,
    )
    page = (ROOT / "public" / "index.html").read_text()
    results = json.loads((ROOT / "results" / "results.json").read_text())

    known: set[str] = set()

    def collect(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
        elif isinstance(node, float):
            known.add(f"{node:.3f}")
            known.add(f"{node:+.3f}")

    collect(results)
    # Only the generated cells, which carry three decimals inside a table or an
    # svg text node. Prose is written by hand and checked by review.
    cells = re.findall(r"<b>(\d\.\d{3})</b>", page) + re.findall(
        r'class="(?:strong|val)"[^>]*>([+-]?\d\.\d{3})', page
    )
    assert cells, "no generated numeric cells found; the selector is wrong"
    unknown = sorted({c for c in cells if c not in known})
    assert not unknown, f"page shows numbers absent from results.json: {unknown}"
