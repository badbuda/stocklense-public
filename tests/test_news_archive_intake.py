"""Provider acquisition tests: locally manufactured ZIP/SEC metadata only."""
import io
import json
import zipfile

import pytest

from news_archive_intake import (
    read_gdelt_zip_bytes, download_gdelt_gkg_file, intake,
)
from news_event_pit import load_journal


def gkg_record(stamp="20150301120000",kind="ARMEDCONFLICT"):
    cols=[""]*27
    cols[0]=stamp+"-testid"
    cols[1]=stamp
    cols[3]="Synthetic Test outlet"
    cols[4]="https://example.invalid/story/"+kind
    cols[7]=kind
    return "\t".join(cols)


def bundle(rows,filename="20150301120000.gkg.csv"):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename,"\n".join(rows)+"\n")
    return out.getvalue()


def test_actual_provider_zip_format_parses_to_private_unverified_records(tmp_path):
    blob=bundle([gkg_record(),gkg_record(kind="UNCLASSIFIED")])
    source=tmp_path/"one.gkg.csv.zip";source.write_bytes(blob)
    output=tmp_path/"my-private-intake.jsonl"
    report=intake(gdelt_zip=source,out=output)
    assert report["status"]=="UNVERIFIED_SOURCE_INTAKE_NOT_FOR_BACKTEST"
    assert report["provider_rows_filtered"]==1
    assert report["point_in_time_first_seen_verified"] is False
    x=load_journal(output)
    assert x["raw_event_records"]==1
    assert x["distinct_verified_stories"]==0
    assert x["status"]=="DATA_BLOCKED_NO_PIT_VERIFIED_EVENTS"


def test_remote_data_api_rejects_unapproved_hosts_paths_or_queries_without_network():
    bad=[
        "https://evil.example/gdeltv2/20150301120000.gkg.csv.zip",
        "http://data.gdeltproject.org/gdeltv2/20150301120000.gkg.csv.zip",
        "https://data.gdeltproject.org/gdeltv2/../../x.gkg.csv.zip",
        "https://data.gdeltproject.org/gdeltv2/20150301120000.gkg.csv.zip?token=x",
        "https://data.gdeltproject.org/gdeltv2/not-a-batch.gkg.csv.zip",
        "https://data.gdeltproject.org.evil.com/gdeltv2/20150301120000.gkg.csv.zip",
    ]
    for uri in bad:
        with pytest.raises(ValueError,match="NEWS_GDELT_ONLY_ALLOWLISTED_15MIN_ARCHIVES"):
            download_gdelt_gkg_file(uri)


def test_archive_traversal_and_multiple_attachments_fail_closed():
    with pytest.raises(ValueError,match="NEWS_GDELT_ARCHIVE_MEMBER_UNSAFE"):
        read_gdelt_zip_bytes(bundle([gkg_record()],"../evil.gkg.csv"))
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("one.gkg.csv",gkg_record()+"\n")
        z.writestr("two.gkg.csv",gkg_record()+"\n")
    with pytest.raises(ValueError,match="NEWS_GDELT_UNEXPECTED_ARCHIVE_MEMBERS"):
        read_gdelt_zip_bytes(buf.getvalue())


def test_sec_official_submission_doc_intake_does_not_infer_merger_or_direction(tmp_path):
    doc={"filings":{"recent":{
      "form":["8-K"],"accessionNumber":["0000320193-24-000001"],
      "primaryDocument":["index.htm"],
      "acceptanceDateTime":["2024-03-20T18:01:00Z"]}}}
    private=tmp_path/"sec.json";private.write_text(json.dumps(doc))
    out=tmp_path/"private-sec-intake.jsonl"
    r=intake(sec_json=private,cik="0000320193",out=out)
    assert r["provider_rows_filtered"]==1
    x=load_journal(out)
    assert x["status"]=="DATA_BLOCKED_NO_PIT_VERIFIED_EVENTS"
    payload=json.loads(out.read_text().splitlines()[0])
    assert payload["category"]=="CORPORATE_FILING"
    assert payload["ticker_mapping_point_in_time_verified"] is False
    assert payload["archived_first_seen_verified"] is False
    assert "body" not in json.dumps(payload).lower()


def test_no_partial_private_file_when_corrupted_provider_input(tmp_path):
    z=tmp_path/"bad.zip";z.write_bytes(bundle(["bad\trow"]))
    out=tmp_path/"should-not-exist.jsonl"
    with pytest.raises(ValueError,match="GDELT_GKG_FIELDS_TRUNCATED"):
        intake(gdelt_zip=z,out=out)
    assert not out.exists()
    with pytest.raises(ValueError,match="NEWS_REQUIRE_EXACTLY_ONE_PROVIDER_INPUT"):
        intake(gdelt_zip=z,sec_json=tmp_path/"sec.json",cik="0000320193",out=out)
