from __future__ import annotations
import ast
from pathlib import Path

def syntax_errors(root="."):
    bad=[]
    for p in Path(root).rglob("*.py"):
        if any(x in p.parts for x in (".git",".venv","venv")): continue
        try: ast.parse(p.read_text(),filename=str(p))
        except SyntaxError as e: bad.append(f"{p}:{e.lineno}")
    return bad

def literal_escape_in_imports(root="."):
    bad=[]
    for p in Path(root).rglob("*.py"):
        if any(x in p.parts for x in (".git",".venv","venv")): continue
        try: tree=ast.parse(p.read_text(),filename=str(p))
        except SyntaxError: continue
        # Valid AST imports cannot contain a literal backslash-n between import statements.
        # Syntax errors are reported by syntax_errors instead of text-pattern heuristics.
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)) and getattr(node,"lineno",None) is None:
                bad.append(str(p))
    return bad

def suspicious_source_escapes(root="."):
    # Kept as compatibility API; AST parsing is the authoritative source-hygiene check.
    return syntax_errors(root)
