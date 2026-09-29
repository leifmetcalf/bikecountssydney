"""Minimal client for querying a publicly embedded Power BI report.

The TfNSW dashboards are Power BI reports embedded with an anonymous embed
token. The same token authorises semantic queries against the report's
dataset, which is how the raw rows are pulled out.
"""

import base64
import json
import threading
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

import httpx

EMBED_INFO_URL = "https://adas.prod.cds.transport.nsw.gov.au/embedinfo/getembedinfo"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
WINDOW = 30_000  # the service caps a query window at 30k rows
TOKEN_MARGIN = 300  # refresh the embed token this many seconds before expiry
DATETIME_TYPE = 7  # DSR type code for datetimes (sent as epoch milliseconds)


class QueryError(RuntimeError):
    pass


# --- semantic query expression builders ---------------------------------------


def column(source: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Source": source}}, "Property": prop}}


def measure(source: str, prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Source": source}}, "Property": prop}}


def literal(value: str | int) -> dict:
    if isinstance(value, str):
        return {"Literal": {"Value": "'" + value.replace("'", "''") + "'"}}
    return {"Literal": {"Value": f"{value}L"}}


def is_in(expr: dict, values) -> dict:
    return {"Condition": {"In": {"Expressions": [expr], "Values": [[literal(v)] for v in values]}}}


# --- client ---------------------------------------------------------------------


class PowerBIClient:
    def __init__(self, report_id: str):
        self.report_id = report_id
        self.http = httpx.Client(timeout=180, headers={"User-Agent": USER_AGENT})
        self._token_lock = threading.Lock()
        self._token = ""
        self._token_expiry = 0.0
        embed_url = self._refresh_token()
        config = json.loads(base64.b64decode(unquote(parse_qs(urlparse(embed_url).query)["config"][0])))
        self.cluster = config["clusterUrl"].rstrip("/")
        model = self._get(f"/explore/reports/{report_id}/modelsAndExploration?preferReadOnlySession=true")["models"][0]
        self.model_id = model["id"]
        self.dataset_id = model["dbName"]

    def _refresh_token(self) -> str:
        # CloudFront caches this response for longer than the token lives; a unique parameter bypasses the cache
        info = self.http.get(EMBED_INFO_URL, params={"reportId": self.report_id, "_": str(time.time_ns())})
        info.raise_for_status()
        info = info.json()
        if isinstance(info, str):  # the endpoint returns JSON encoded as a JSON string
            info = json.loads(info)
        self._token = info["EmbedToken"]["Token"]
        self._token_expiry = datetime.fromisoformat(info["EmbedToken"]["Expiration"]).timestamp()
        return info["EmbedReport"][0]["EmbedUrl"]

    def _auth(self, force_refresh: bool = False) -> dict:
        with self._token_lock:
            if force_refresh or time.time() > self._token_expiry - TOKEN_MARGIN:
                self._refresh_token()
            return {"Authorization": f"EmbedToken {self._token}"}

    def _get(self, path: str) -> dict:
        r = self.http.get(self.cluster + path, headers=self._auth())
        r.raise_for_status()
        return r.json()

    def schema(self) -> dict[str, list[tuple[str, str]]]:
        """Map each entity to its (property name, "column" | "measure") pairs, hidden ones included."""
        r = self.http.post(
            self.cluster + "/explore/conceptualschema",
            headers=self._auth(),
            json={"modelIds": [self.model_id], "userPreferredLocale": "en-US"},
        )
        r.raise_for_status()
        entities = r.json()["schemas"][0]["schema"]["Entities"]
        return {
            e["Name"]: [(p["Name"], "measure" if "Measure" in p else "column") for p in e.get("Properties", [])]
            for e in entities
        }

    def _post_query(self, body: dict, retries: int = 6) -> dict:
        force_refresh = False
        for attempt in range(retries):
            try:
                headers = self._auth(force_refresh) | {"ActivityId": str(uuid.uuid4()), "RequestId": str(uuid.uuid4())}
                r = self.http.post(self.cluster + "/explore/querydata?synchronous=true", headers=headers, json=body)
                if r.status_code in (401, 403):
                    force_refresh = True
                    raise httpx.HTTPStatusError("auth", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()["results"][0]["result"]["data"]
                error = data["dsr"]["DS"][0].get("odata.error")
                if error:
                    raise QueryError(json.dumps(error))
                return data
            except (httpx.HTTPError, QueryError, KeyError):
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def query_window(self, entities, select, where=(), restart=None) -> tuple[list[str], list[list], list | None]:
        """Run one query window: returns (column names, rows, restart tokens or None when complete)."""
        query = {
            "Version": 2,
            "From": [{"Name": alias, "Entity": entity, "Type": 0} for alias, entity in entities],
            "Select": [expr | {"Name": name} for name, expr in select],
        }
        if where:
            query["Where"] = list(where)
        window = {"Count": WINDOW} | ({"RestartTokens": restart} if restart else {})
        command = {
            "Query": query,
            "Binding": {
                "Primary": {"Groupings": [{"Projections": list(range(len(select)))}]},
                "DataReduction": {"DataVolume": 4, "Primary": {"Window": window}},
                "Version": 1,
            },
            "ExecutionMetricsKind": 1,
        }
        body = {
            "version": "1.0.0",
            "queries": [
                {
                    "Query": {"Commands": [{"SemanticQueryDataShapeCommand": command}]},
                    "QueryId": "",
                    "ApplicationContext": {"DatasetId": self.dataset_id, "Sources": [{"ReportId": self.report_id}]},
                }
            ],
            "cancelQueries": [],
            "modelId": self.model_id,
        }
        data = self._post_query(body)
        names = [s["Name"] for s in data["descriptor"]["Select"]]
        ds = data["dsr"]["DS"][0]
        return names, decode_dsr(ds), ds.get("RT")

    def query(self, entities, select, where=()) -> tuple[list[str], list[list]]:
        """Run a query to completion, following restart tokens across windows."""
        names, rows, restart = self.query_window(entities, select, where)
        while restart:
            _, page, restart = self.query_window(entities, select, where, restart)
            # each continuation window starts with the row its restart token points at
            if page and rows and page[0] == rows[-1]:
                page = page[1:]
            rows.extend(page)
        return names, rows


def decode_dsr(ds: dict) -> list[list]:
    """Expand the compressed DSR row format: repeat (R) and null (Ø) bitmasks plus value dictionaries."""
    value_dicts = ds.get("ValueDicts", {})
    rows: list[list] = []
    schema: list[dict] = []
    prev: list = []
    for ph in ds.get("PH", []):
        for row in ph.get("DM0", []):
            schema = row.get("S", schema)
            repeat, null = row.get("R", 0), row.get("Ø", 0)
            values = iter(row.get("C", []))
            out = []
            for i, col in enumerate(schema):
                if repeat >> i & 1:
                    out.append(prev[i])
                    continue
                if null >> i & 1:
                    out.append(None)
                    continue
                v = next(values)
                if "DN" in col and isinstance(v, int):
                    v = value_dicts[col["DN"]][v]
                elif col.get("T") == DATETIME_TYPE and isinstance(v, int):
                    v = datetime.fromtimestamp(v / 1000, UTC).replace(tzinfo=None).isoformat()
                out.append(v)
            rows.append(out)
            prev = out
    return rows
