#!/usr/bin/env python3
"""
es-cli — Elasticsearch inspector for local dev clusters
Usage: es-cli [command] [options]

Commands:
  indices               List all indices with doc count, size, status
  schema  <index>       Show field mappings for an index
  stats   <index>       Detailed index stats (docs, store, shards)
  sample  <index>       Print N sample documents (default 5)
  search  <index> <q>   Full-text search and print hits
  logs    [n]           Inspect llm-proxy-logs (newest N entries, default 10)
  delete  <index>       Delete an index (prompts for confirmation)

Options:
  --host    ES host URL  (default: http://localhost:9200)
  --n       Number of rows for sample/logs/search  (default: 5)
  --pretty  Pretty-print JSON bodies in logs output

Usage:
    es-cli indices
    es-cli schema llm-proxy-logs
    es-cli stats  llm-proxy-logs
    es-cli sample llm-proxy-logs --n 5
    es-cli logs 20 --pretty
    es-cli search llm-proxy-logs "gpt-4o"
    es-cli delete some-index

All commands default to http://localhost:9200 — override with --host. The logs command has special handling for llm-proxy-logs: it surfaces model, message count, last user message, token usage, and truncated response inline without needing --pretty.
"""

import argparse
import json
import sys
import textwrap
from datetime import datetime
from typing import Any

try:
    import httpx
except ImportError:
    sys.exit("httpx not found — pip install httpx")

# ── ANSI ─────────────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
B = "\033[94m"
C = "\033[96m"
RESET = "\033[0m"


def hr(char="─", width=72):
    print(char * width)


def h1(text):
    print(f"\n{BOLD}{text}{RESET}")


def label(k, v, kw=22):
    print(f"  {DIM}{k:<{kw}}{RESET}{v}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def get(host: str, path: str, params: dict | None = None) -> Any:
    url = host.rstrip("/") + path
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        sys.exit(
            f"{R}Cannot connect to Elasticsearch at {host}{RESET}\n"
            "  Is it running? Check: docker compose ps"
        )
    except httpx.HTTPStatusError as e:
        sys.exit(f"{R}HTTP {e.response.status_code}{RESET}: {e.response.text[:300]}")


def post(host: str, path: str, body: dict) -> Any:
    url = host.rstrip("/") + path
    try:
        r = httpx.post(url, json=body, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        sys.exit(f"{R}Cannot connect to Elasticsearch at {host}{RESET}")
    except httpx.HTTPStatusError as e:
        sys.exit(f"{R}HTTP {e.response.status_code}{RESET}: {e.response.text[:300]}")


def delete_req(host: str, path: str) -> Any:
    url = host.rstrip("/") + path
    r = httpx.delete(url, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_indices(host: str, **_):
    data = get(host, "/_cat/indices?v=true&s=index&format=json")
    if not data:
        print("No indices found.")
        return

    h1("Indices")
    print(f"  {'Index':<35} {'Status':<8} {'Docs':>10} {'Deleted':>9} {'Size':>10}")
    hr()
    for idx in data:
        name = idx.get("index", "")
        status = idx.get("health", "")
        docs = idx.get("docs.count", "0") or "0"
        deleted = idx.get("docs.deleted", "0") or "0"
        size = idx.get("store.size", "?")
        color = G if status == "green" else Y if status == "yellow" else R
        print(
            f"  {B}{name:<35}{RESET} {color}{status:<8}{RESET} "
            f"{int(docs):>10,} {int(deleted):>9,} {size:>10}"
        )
    print()


def cmd_schema(host: str, index: str, **_):
    data = get(host, f"/{index}/_mapping")
    mappings = data.get(index, {}).get("mappings", {})
    props = mappings.get("properties", {})

    h1(f"Schema: {index}")
    if not props:
        print("  (no properties found)")
        return

    def _print_props(d: dict, indent=0):
        pad = "  " * indent
        for field, meta in sorted(d.items()):
            ftype = meta.get("type", "object")
            color = (
                C
                if ftype in ("keyword", "text")
                else (
                    Y
                    if ftype in ("date", "long", "integer", "short", "float", "double")
                    else DIM
                )
            )
            sub = meta.get("properties", {})
            sub_note = f" {DIM}({len(sub)} sub-fields){RESET}" if sub else ""
            print(f"  {pad}{B}{field}{RESET}: {color}{ftype}{RESET}{sub_note}")
            if sub:
                _print_props(sub, indent + 1)

    hr()
    _print_props(props)
    print()


def cmd_stats(host: str, index: str, **_):
    data = get(host, f"/{index}/_stats")
    total = data.get("_all", {}).get("total", {})

    h1(f"Stats: {index}")
    hr()
    docs = total.get("docs", {})
    store = total.get("store", {})
    label("Documents", f"{docs.get('count', 0):,}")
    label("Deleted", f"{docs.get('deleted', 0):,}")
    label(
        "Store size",
        f"{store.get('size_in_bytes', 0) / 1024:.1f} KB  "
        f"({store.get('size_in_bytes', 0):,} bytes)",
    )

    # shard info from _cat/shards
    shards = get(host, f"/_cat/shards/{index}?format=json")
    if shards:
        print(f"\n  {DIM}Shards:{RESET}")
        for s in shards:
            state = s.get("state", "")
            color = G if state == "STARTED" else Y
            print(
                f"    [{s.get('shard')}] {color}{state:<12}{RESET} "
                f"node={s.get('node','?')}  docs={s.get('docs','?')}"
            )
    print()


def _fmt_body(body: Any, pretty: bool, max_chars: int = 300) -> str:
    if body is None:
        return f"{DIM}null{RESET}"
    if isinstance(body, dict):
        s = json.dumps(body, indent=2 if pretty else None, ensure_ascii=False)
    else:
        s = str(body)
    if len(s) > max_chars and not pretty:
        s = s[:max_chars] + f"  {DIM}… (truncated){RESET}"
    return s


def cmd_sample(host: str, index: str, n: int = 5, pretty: bool = False, **_):
    body = {"size": n, "query": {"match_all": {}}}
    data = post(host, f"/{index}/_search", body)
    hits = data.get("hits", {}).get("hits", [])
    total = data.get("hits", {}).get("total", {}).get("value", 0)

    h1(f"Sample ({len(hits)} of {total:,} docs): {index}")
    for i, hit in enumerate(hits, 1):
        hr("─")
        print(f"  {BOLD}[{i}]{RESET}  _id={C}{hit['_id']}{RESET}")
        src = hit.get("_source", {})
        for k, v in src.items():
            v_str = _fmt_body(v, pretty)
            print(f"       {DIM}{k}{RESET}: {v_str}")
    hr()
    print()


def cmd_search(
    host: str, index: str, query: str, n: int = 5, pretty: bool = False, **_
):
    body = {
        "size": n,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["*"],
                "type": "best_fields",
            }
        },
    }
    data = post(host, f"/{index}/_search", body)
    hits = data.get("hits", {}).get("hits", [])
    total = data.get("hits", {}).get("total", {}).get("value", 0)

    h1(f"Search '{query}' — {total:,} hits (showing {len(hits)}): {index}")
    for i, hit in enumerate(hits, 1):
        hr("─")
        score = hit.get("_score", 0)
        print(
            f"  {BOLD}[{i}]{RESET}  _id={C}{hit['_id']}{RESET}  score={Y}{score:.3f}{RESET}"
        )
        for k, v in hit.get("_source", {}).items():
            v_str = _fmt_body(v, pretty)
            print(f"       {DIM}{k}{RESET}: {v_str}")
    hr()
    print()


def cmd_logs(host: str, n: int = 10, pretty: bool = False, **_):
    """Tailored view for llm-proxy-logs index."""
    INDEX = "llm-proxy-logs"

    # check index exists
    indices = get(host, "/_cat/indices?format=json&s=index")
    names = [i["index"] for i in indices]
    if INDEX not in names:
        print(
            f"{Y}Index '{INDEX}' not found.{RESET}  Available: {', '.join(names) or 'none'}"
        )
        return

    body = {
        "size": n,
        "sort": [{"timestamp": {"order": "desc"}}],
        "query": {"match_all": {}},
    }
    data = post(host, f"/{INDEX}/_search", body)
    hits = data.get("hits", {}).get("hits", [])
    total = data.get("hits", {}).get("total", {}).get("value", 0)

    h1(f"LLM Proxy Logs — newest {len(hits)} of {total:,}")
    hr()

    for hit in hits:
        src = hit.get("_source", {})
        ts = src.get("timestamp", "?")
        method = src.get("method", "?")
        path = src.get("path", "?")
        status = src.get("status_code", "?")
        req_id = src.get("request_id", "")[:8]

        status_color = G if str(status).startswith("2") else R
        print(
            f"  {DIM}{ts}{RESET}  "
            f"{Y}{method:<6}{RESET} "
            f"{B}{path}{RESET}  "
            f"{status_color}{status}{RESET}  "
            f"{DIM}id={req_id}…{RESET}"
        )

        # Request body highlights
        req_body = src.get("request_body") or {}
        if isinstance(req_body, dict):
            model = req_body.get("model", "")
            messages = req_body.get("messages", [])
            msg_count = len(messages)
            last_msg = messages[-1].get("content", "")[:120] if messages else ""
            if model:
                print(f"    {DIM}model{RESET}      {C}{model}{RESET}")
            if last_msg:
                print(
                    f"    {DIM}last_msg{RESET}   {textwrap.shorten(str(last_msg), 100)}"
                )
            if msg_count:
                print(f"    {DIM}msg_count{RESET}  {msg_count}")

        # Response body highlights
        resp_body = src.get("response_body") or {}
        if isinstance(resp_body, dict):
            usage = resp_body.get("usage", {})
            if usage:
                pt = usage.get("prompt_tokens", 0)
                ct = usage.get("completion_tokens", 0)
                label("tokens (p/c)", f"{pt} / {ct}", kw=16)
            choices = resp_body.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                if content:
                    print(
                        f"    {DIM}response{RESET}   {textwrap.shorten(str(content), 120)}"
                    )

        if pretty:
            print(f"\n    {DIM}--- request_body ---{RESET}")
            print(
                textwrap.indent(
                    json.dumps(req_body, indent=2, ensure_ascii=False), "    "
                )
            )
            print(f"\n    {DIM}--- response_body ---{RESET}")
            print(
                textwrap.indent(
                    json.dumps(resp_body, indent=2, ensure_ascii=False), "    "
                )
            )

        hr("·")
    print()


def cmd_delete(host: str, index: str, **_):
    confirm = input(
        f"{R}Delete index '{index}'? This is irreversible. Type the index name to confirm: {RESET}"
    )
    if confirm.strip() != index:
        print("Aborted.")
        return
    delete_req(host, f"/{index}")
    print(f"{G}Deleted: {index}{RESET}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        description="Elasticsearch inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "command",
        choices=["indices", "schema", "stats", "sample", "search", "logs", "delete"],
        help="Command to run",
    )
    p.add_argument("args", nargs="*", help="index / query arguments")
    p.add_argument("--host", default="http://localhost:9200", help="ES host URL")
    p.add_argument("--n", type=int, default=5, help="Number of documents to return")
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON request/response bodies",
    )

    args = p.parse_args()
    cmd = args.command
    rest = args.args

    if cmd == "indices":
        cmd_indices(host=args.host)

    elif cmd == "schema":
        if not rest:
            sys.exit("Usage: es_cli.py schema <index>")
        cmd_schema(host=args.host, index=rest[0])

    elif cmd == "stats":
        if not rest:
            sys.exit("Usage: es_cli.py stats <index>")
        cmd_stats(host=args.host, index=rest[0])

    elif cmd == "sample":
        if not rest:
            sys.exit("Usage: es_cli.py sample <index> [--n N]")
        cmd_sample(host=args.host, index=rest[0], n=args.n, pretty=args.pretty)

    elif cmd == "search":
        if len(rest) < 2:
            sys.exit("Usage: es_cli.py search <index> <query>")
        cmd_search(
            host=args.host,
            index=rest[0],
            query=" ".join(rest[1:]),
            n=args.n,
            pretty=args.pretty,
        )

    elif cmd == "logs":
        n = int(rest[0]) if rest else args.n
        cmd_logs(host=args.host, n=n, pretty=args.pretty)

    elif cmd == "delete":
        if not rest:
            sys.exit("Usage: es_cli.py delete <index>")
        cmd_delete(host=args.host, index=rest[0])


if __name__ == "__main__":
    main()
