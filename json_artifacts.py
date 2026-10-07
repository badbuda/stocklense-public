from __future__ import annotations
import json,os,tempfile
from pathlib import Path
def write_json_atomic(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(obj,indent=2)+"\n"
    json.loads(payload)
    fd,tmp=tempfile.mkstemp(prefix=p.name+".",dir=p.parent)
    try:
        with os.fdopen(fd,"w") as f:f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return obj
def validate_json_files(paths):
    bad=[]
    for path in paths:
        p=Path(path)
        if not p.exists():bad.append({"path":path,"error":"MISSING"});continue
        try:json.loads(p.read_text())
        except Exception as e:bad.append({"path":path,"error":type(e).__name__})
    return bad
