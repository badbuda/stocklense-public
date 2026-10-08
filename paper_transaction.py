"""Recoverable, fail-closed local paper session writes. No broker orders.

The prepared snapshot is durable before any evidence is modified. Each target
file is atomically replaced; interrupted writes resume the exact prepared bytes.
GitHub publishes all artifacts in one git commit, so a failed uncommitted
GitHub runner does NOT persist the pending snapshot to the next runner.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path

PARTS = ("trades", "ledger", "state", "latest")
OPTIONAL_PARTS = ("snapshot",)

class PaperTransactionError(RuntimeError):
    pass

def digest(blob):
    return hashlib.sha256(blob).hexdigest() if blob is not None else None

def read(path):
    return path.read_bytes() if path.is_file() else None

def atomic_replace(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="._paper_", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def add_csv_rows(path, new_rows):
    old = read(path)
    if not new_rows:
        return old
    fields, previous = [], []
    if old:
        reader = csv.DictReader(io.StringIO(old.decode("utf-8"), newline=""))
        fields = list(reader.fieldnames or [])
        previous = list(reader)
        if not fields:
            raise PaperTransactionError("CSV_HEADER_MISSING")
    for new in new_rows:
        for key in new:
            if key not in fields:
                fields.append(key)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(previous)
    writer.writerows(new_rows)
    return out.getvalue().encode("utf-8")

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")

def _folder(paths):
    return paths["state"].parent / ".transactions"

def _read_prepared(path):
    envelope = json.loads(path.read_text(encoding="utf-8"))
    head = {k:v for k,v in envelope.items() if k!="manifest_sha256"}
    if (envelope.get("manifest_sha256")!=digest(canonical(head))
        or envelope.get("schema_version")!=1 or
        set(envelope.get("pieces",{})) not in (set(PARTS),set(PARTS+OPTIONAL_PARTS))):
        raise PaperTransactionError("CORRUPT_PAPER_PREPARE_RECORD")
    return envelope

def _finish(path, paths):
    pending = _read_prepared(path)
    for kind in pending["pieces"]:
        if kind not in paths:
            raise PaperTransactionError("MISSING_PREPARED_DESTINATION:"+kind)
        info = pending["pieces"][kind]
        target = paths[kind]
        content = info["after"].encode("utf-8") if info["after"] is not None else None
        new_hash = digest(content)
        if info["after_sha256"]!=new_hash:
            raise PaperTransactionError("CORRUPT_PREPARED_OUTPUT:"+kind)
        current_hash = digest(read(target))
        if current_hash==new_hash:
            continue
        if current_hash!=info["before_sha256"]:
            raise PaperTransactionError("EXTERNAL_PAPER_DRIFT:"+kind)
        if content is None:
            raise PaperTransactionError("UNEXPECTED_PAPER_FILE_REMOVAL")
        atomic_replace(target,content)
        if digest(read(target))!=new_hash:
            raise PaperTransactionError("PAPER_REPLACE_FAILED:"+kind)
    path.unlink()
    return {"session_date":pending["session_date"],"equity":pending["equity"],
            "drawdown":pending["drawdown"],"trades":pending["trades_count"]}

def recover(paths):
    folder = _folder(paths)
    jobs = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if len(jobs)>1:
        raise PaperTransactionError("MULTIPLE_PENDING_PAPER_SESSIONS")
    return _finish(jobs[0],paths) if jobs else None

def commit(paths,row,trades,state,latest_markdown):
    if recover(paths):
        raise PaperTransactionError("RECOVERED_OLD_TRANSACTION_RETRY")
    day = row["session_date"]
    if len(day)!=10 or day[4]!="-" or day[7]!="-":
        raise PaperTransactionError("INVALID_PAPER_SESSION_DATE")
    pending = _folder(paths)/(day+".json")
    payloads = {
        "trades":add_csv_rows(paths["trades"],trades),
        "ledger":add_csv_rows(paths["ledger"],[row]),
        "state":json.dumps(state,indent=2,ensure_ascii=False).encode(),
        "latest":latest_markdown.encode(),
    }
    if "snapshot" in paths:
        payloads["snapshot"] = canonical({
            "schema_version": 1, "session_date": day,
            "broker_fills_observed": False, "row": row, "trades": trades,
        })
    pieces={}
    for kind,blob in payloads.items():
        pieces[kind]={"before_sha256":digest(read(paths[kind])),
                      "after":blob.decode() if blob is not None else None,
                      "after_sha256":digest(blob)}
    record={"schema_version":1,"session_date":day,"equity":float(row["equity"]),
            "drawdown":float(row["drawdown"]),"trades_count":len(trades),"pieces":pieces}
    record["manifest_sha256"]=digest(canonical(record))
    atomic_replace(pending,json.dumps(record,indent=2,ensure_ascii=False).encode())
    return _finish(pending,paths)
