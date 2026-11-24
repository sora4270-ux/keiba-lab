#!/usr/bin/env python3
"""Append-only cryptographic ledger for newly frozen NAR forecast payloads.

Records hashes of first-observed frozen fields. Never changes forecasts.
Git history provides an independent sequence of ledger commits, but not proof
that a forecast was actually captured before the race cutoff.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

FORECAST = Path("data/auto/nar_predictions.json")
LEDGER = Path("data/auto/nar_frozen_ledger.json")
FROZEN = ("id","date","venue","race_no","start_at","cutoff_at","locked_at",
          "predicted_at","ranking","tickets","market_at_lock","strategy_v5","entry_context_at_lock")


def digest(record):
    immutable = {k:record[k] for k in FROZEN if k in record}
    raw=json.dumps(immutable,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def update_ledger(predictions, ledger, observed_at):
    if not isinstance(predictions,dict) or not isinstance(predictions.get("races"),list):
        raise ValueError("Invalid NAR prediction history")
    if not isinstance(ledger,dict) or ledger.get("schema_version")!=1 or not isinstance(ledger.get("entries"),list):
        raise ValueError("Invalid NAR ledger")
    seen={}
    for entry in ledger["entries"]:
        if not isinstance(entry,dict) or not isinstance(entry.get("id"),str) or not isinstance(entry.get("sha256"),str) or entry["id"] in seen:
            raise ValueError("Invalid or duplicate ledger entry")
        seen[entry["id"]]=entry
    new=[]
    found=set()
    for r in predictions["races"]:
        if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"] or r["id"] in found:
            raise ValueError("Invalid or duplicate frozen race ID")
        found.add(r["id"])
        h=digest(r)
        if r["id"] in seen:
            if h!=seen[r["id"]]["sha256"]:
                raise RuntimeError("Frozen snapshot changed: "+r["id"])
        else:
            try:
                cutoff=dt.datetime.fromisoformat(r["cutoff_at"])
                locked=dt.datetime.fromisoformat(r["locked_at"])
                observed=dt.datetime.fromisoformat(observed_at)
                if any(x.tzinfo is None for x in (cutoff,locked,observed)):
                    raise ValueError("Naive timestamp")
                status="observed_before_cutoff" if observed<cutoff and locked<=observed else "historical_import_not_authenticated"
            except (KeyError,ValueError,TypeError):
                status="historical_import_not_authenticated"
            new.append({"id":r["id"],"sha256":h,"first_seen_at":observed_at,
                        "observation_status":status})
    # Never silently lose an entry, even if old forecast history is truncated.
    missing=set(seen)-found
    if missing:
        raise RuntimeError(f"Ledger history missing {len(missing)} previously frozen races")
    return {"schema_version":1,"entries":ledger["entries"]+new},len(new)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=FORECAST)
    p.add_argument("--ledger",type=Path,default=LEDGER)
    a=p.parse_args()
    predictions=json.loads(a.input.read_text(encoding="utf-8"))
    ledger=json.loads(a.ledger.read_text(encoding="utf-8")) if a.ledger.exists() else {"schema_version":1,"entries":[]}
    observed=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    result,n=update_ledger(predictions,ledger,observed)
    a.ledger.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.ledger.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    tmp.replace(a.ledger)
    print(f"NAR ledger: {len(result['entries'])} entries, {n} new; timestamps are not independently authenticated")


if __name__=="__main__":
    main()
