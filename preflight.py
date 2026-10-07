from __future__ import annotations
import ast
import compileall
import json
from pathlib import Path

SKIP={".git",".venv","venv"}

def run_preflight():
    ok=compileall.compile_dir(".",quiet=1,maxlevels=10)
    py=sum(1 for p in Path(".").rglob("*.py") if not any(x in SKIP for x in p.parts))
    malformed=[]
    for p in Path("tests").rglob("*.py"):
        try:
            ast.parse(p.read_text(),filename=str(p))
        except SyntaxError as e:
            malformed.append({"path":str(p),"line":e.lineno,"message":e.msg})
    result={
        "status":"PASS" if ok and not malformed else "FAIL",
        "python_files_discovered":py,
        "compileall":ok,
        "syntax_errors":malformed,
    }
    Path("shadow_history").mkdir(exist_ok=True)
    Path("shadow_history/preflight.json").write_text(json.dumps(result,indent=2)+"\n")
    if not ok or malformed:
        raise SystemExit(2)
    return result

if __name__=="__main__":
    print(json.dumps(run_preflight(),indent=2))
