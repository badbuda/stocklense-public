from __future__ import annotations
import subprocess,sys
def main():
    subprocess.run(["git","fetch","origin","main"],check=True)
    base=subprocess.check_output(["git","merge-base","HEAD","origin/main"],text=True).strip()
    remote=subprocess.check_output(["git","rev-parse","origin/main"],text=True).strip()
    if base!=remote:
        print("STALE_BRANCH: branch does not contain current origin/main; rebase before integration.")
        return 2
    print("BRANCH_BASE_OK")
    return 0
if __name__=="__main__":sys.exit(main())
