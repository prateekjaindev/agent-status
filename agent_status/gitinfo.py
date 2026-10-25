"""Branch and uncommitted changes for an agent's working directory, cached briefly."""
import os, re, subprocess

TTL = 15
_cache = {}


def _git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2)


def git_info(cwd, now):
    if not cwd or not os.path.isdir(cwd):
        return None
    hit = _cache.get(cwd)
    if hit and now - hit[0] < TTL:
        return hit[1]
    info = None
    try:
        st = _git(cwd, "status", "--porcelain=v2", "--branch")
        if st.returncode == 0:
            lines = st.stdout.splitlines()
            branch = next((l.split(" ", 2)[2] for l in lines if l.startswith("# branch.head ")), None)
            diff = _git(cwd, "diff", "HEAD", "--shortstat").stdout  # fails harmlessly before the first commit
            add, rem = (int(m[1]) if (m := re.search(rf"(\d+) {w}", diff)) else 0 for w in ("insertion", "deletion"))
            info = dict(branch=branch, files=sum(1 for l in lines if l and not l.startswith("#")), add=add, rem=rem)
    except (OSError, subprocess.TimeoutExpired):
        pass
    _cache[cwd] = (now, info)
    return info
