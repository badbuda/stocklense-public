"""Bounded raw provider intake: actual GDELT GKG ZIP/TSV or SEC JSON.

Usage (owner's PRIVATE workstation, NOT CI; not a trading application):
  python news_archive_intake.py --gdelt-gkg-zip /private/20150301120000.gkg.csv.zip
  python news_archive_intake.py --gdelt-gkg-url https://data.gdeltproject.org/gdeltv2/20260301120000.gkg.csv.zip
  python news_archive_intake.py --sec-submissions-json /private/CIK0000320193.json --cik 0000320193

Records are marked *UNVERIFIED for historical trading* regardless of archive
file time; SEC acceptance and GDELT GKG observation alone do not certify
executable first-seen time, prospectively delivered model inference, SEC item
semantics, or a historical ticker/CIK mapping. No article bodies or API tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

from news_provider_adapters import gdelt_2_gkg_row_to_event, sec_submission_rows
from news_event_pit import clean_event

OUT=Path("research/data/news_provider_intake_PRIVATE_unverified.jsonl")
MAX_ZIP_BYTES=32*1024*1024
MAX_EXPANDED_BYTES=128*1024*1024
MAX_ROWS=100000
ALLOWED_GDELT_HOST="data.gdeltproject.org"


def read_gdelt_zip_bytes(blob):
    if len(blob)>MAX_ZIP_BYTES:
        raise ValueError("NEWS_GDELT_ARCHIVE_EXCEEDS_SIZE_LIMIT")
    z=zipfile.ZipFile(io.BytesIO(blob))
    members=[x for x in z.infolist() if not x.is_dir()]
    if len(members)!=1:
        raise ValueError("NEWS_GDELT_UNEXPECTED_ARCHIVE_MEMBERS")
    m=members[0]
    if ("/" in m.filename or "\\" in m.filename or ".." in m.filename
        or m.file_size>MAX_EXPANDED_BYTES or not m.filename.endswith(
             (".gkg.csv",".gkg.tsv",".csv",".tsv"))):
        raise ValueError("NEWS_GDELT_ARCHIVE_MEMBER_UNSAFE")
    # No extract-to-disk and no article full text; stream bounded rows.
    out=[]
    with z.open(m,"r") as stream:
        for ix,raw in enumerate(stream):
            if ix>=MAX_ROWS:
                raise ValueError("NEWS_GDELT_ARCHIVE_ROW_LIMIT")
            if len(raw)>1_000_000:
                raise ValueError("NEWS_GDELT_UNBOUNDED_RECORD")
            try:row=raw.decode("utf-8",errors="strict").rstrip("\n\r")
            except UnicodeError as exc:
                raise ValueError("NEWS_GDELT_INVALID_UTF8") from exc
            if not row:continue
            parsed=gdelt_2_gkg_row_to_event(row)
            if parsed["category"]=="UNCLASSIFIED_NEWS":
                continue  # no invented conflict/war signal
            out.append(parsed)
    return out


def download_gdelt_gkg_file(url):
    parsed=urlsplit(url)
    if (parsed.scheme!="https" or parsed.netloc!=ALLOWED_GDELT_HOST
        or not re.fullmatch(r"/gdeltv2/\d{14}\.gkg\.csv\.zip",parsed.path)
        or parsed.query or parsed.fragment or parsed.username):
        raise ValueError("NEWS_GDELT_ONLY_ALLOWLISTED_15MIN_ARCHIVES")
    req=__import__("urllib.request",fromlist=["Request"]).Request(
        url,headers={"User-Agent":"StockLens-Research-Archive/1.0 (offline replay)"})
    with urlopen(req,timeout=20) as r:
        if r.status!=200:raise ValueError("NEWS_GDELT_HTTP_FAILURE")
        blob=r.read(MAX_ZIP_BYTES+1)
    if len(blob)>MAX_ZIP_BYTES:
        raise ValueError("NEWS_GDELT_ARCHIVE_EXCEEDS_SIZE_LIMIT")
    return blob


def intake(*,gdelt_zip=None,gdelt_url=None,sec_json=None,cik=None,out=OUT):
    options=sum(x is not None for x in (gdelt_zip,gdelt_url,sec_json))
    if options!=1:
        raise ValueError("NEWS_REQUIRE_EXACTLY_ONE_PROVIDER_INPUT")
    if gdelt_zip is not None:
        blob=Path(gdelt_zip).read_bytes()
        batch=read_gdelt_zip_bytes(blob)
        source_sha=hashlib.sha256(blob).hexdigest()
    elif gdelt_url is not None:
        blob=download_gdelt_gkg_file(gdelt_url)
        batch=read_gdelt_zip_bytes(blob)
        source_sha=hashlib.sha256(blob).hexdigest()
    else:
        if cik is None:raise ValueError("NEWS_SEC_CIK_REQUIRED")
        blob=Path(sec_json).read_bytes()
        batch=sec_submission_rows(json.loads(blob),cik=cik)
        source_sha=hashlib.sha256(blob).hexdigest()
    # Process records first, then write. No incomplete journal on error.
    accepted=[clean_event(x) for x in batch]
    if any(x["first_seen_proven"] for x in accepted):
        raise ValueError("NEWS_PROVIDER_INTAKE_NEVER_ATTESTS_TRADE_FIRST_SEEN")
    # Output *source record metadata only*, never headlines/article body.
    dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    raw="".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n"
                for x in batch)
    dest.write_text(raw,encoding="utf-8")
    return {
        "status":"UNVERIFIED_SOURCE_INTAKE_NOT_FOR_BACKTEST",
        "raw_provider_file_sha256":source_sha,
        "provider_rows_filtered":len(accepted),
        "output_source_metadata_jsonl_sha256":hashlib.sha256(raw.encode()).hexdigest(),
        "private_output":str(dest),
        "point_in_time_first_seen_verified":False,
        "historic_trade_alpha_evidence":False,
        "capital_deployment_authorized":False
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--gdelt-gkg-zip")
    group.add_argument("--gdelt-gkg-url")
    group.add_argument("--sec-submissions-json")
    p.add_argument("--cik",help="Original issuer ten-digit CIK for SEC filings")
    p.add_argument("--out",default=str(OUT))
    a=p.parse_args()
    report=intake(gdelt_zip=a.gdelt_gkg_zip,gdelt_url=a.gdelt_gkg_url,
                  sec_json=a.sec_submissions_json,cik=a.cik,out=a.out)
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
