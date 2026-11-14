#!/usr/bin/env python3
"""Task system: GitHub issues in the task repos, claimed through `claim/<number>` branches.

Task repos are this workspace's own repo (the home repo, `origin`) plus every
repos.yaml entry with `tasks: true` or `tasks: assigned`. A task is addressed by its ref:
`81` (or `#81`) for the home repo, `<repo>#81` for another task repo (`<repo>` = its
repos.yaml name). Everything about a task lives in the task's own repo, so collaborators
on that repo see all of it: the issue, its claim branch and its card images (branch `cards`).

An issue's GitHub assignee is who it belongs to: that person's agents work on it and its
decision card waits on them. This workspace's agents pick up only the owner's issues
(`github` in workspace.yaml): those assigned to them, plus unassigned ones in the home repo
and in `tasks: true` repos. In a `tasks: assigned` repo (shared with collaborators) an
unassigned issue belongs to nobody yet and waits until someone assigns it.

Issues hold the task (Goal / Done when / Plan / Next; Log as comments). Every open issue
carries one status label (see OPEN); closing it means done or dropped. A claim says
who holds the issue right now and is a commit on branch `claim/<number>` of its repo:

  tip message "claim #N by <id>"    -> taken by <id>
  tip message "release #N by <id>"  -> free (and worked on before)
  no branch                         -> free (never started)

Every state change is a new commit whose parent is the tip we just read, pushed
without force. If two agents race, both build on the same tip, GitHub accepts the
first push and rejects the second as non-fast-forward. That is the lock. Releasing
never deletes the branch (cloud sessions may not delete refs); `prune` cleans up
branches of closed issues where deleting is allowed.

Issue reads and writes go through `gh api` (REST).
"""
import argparse, datetime, getpass, json, os, re, socket, subprocess, sys, uuid
from pathlib import Path



def workspace_root():
    """The workspace this script serves: $WORKSPACE_ROOT, else the nearest folder above the
    script (path not resolved, so a `scripts/task.py` symlink counts) that holds repos.yaml
    or workspace.yaml, else the folder above scripts/ (a standalone core checkout)."""
    if os.environ.get("WORKSPACE_ROOT"):
        return os.environ["WORKSPACE_ROOT"]
    here = os.path.dirname(os.path.abspath(__file__))
    d = os.path.dirname(here)
    while True:
        if any(os.path.exists(os.path.join(d, f)) for f in ("repos.yaml", "workspace.yaml")):
            return d
        if os.path.dirname(d) == d:
            return os.path.dirname(here)
        d = os.path.dirname(d)


ROOT = workspace_root()
PREFIX = "claim/"
STALE_HOURS = 2
# Open statuses, one label each, in `list` order (what needs the owner first, backlog last).
#   in-review  the owner's turn: an answer, a decision or an input only they can give; comes with a decision card
#   ready  an agent's turn: picked up by `take`, worked on while claimed
#   on-hold    waits for a condition (another issue, an event, a date); agents re-check it each run
#   backlog    an idea, or not specified enough to start; never picked up
OPEN = ["in-review", "ready", "on-hold", "backlog"]
# Statuses that carry a `Waiting on:` line (what the owner must do / the condition to wait for).
NEEDS_NOTE = ("in-review", "on-hold")
STATUSES = OPEN + ["done", "dropped"]  # the last two close the issue
# Who works on a ready issue: label `agent:<name>`; no such label means the developer agent (autopilot).
#   dev  code, tests, landing changes (the autopilot skill)
#   pm   product work: user data, feedback, research, proposals; no code (the product-manager skill)
AGENTS = ["dev", "pm"]


def engines():
    """Execution engines a task may be pinned to (`worker:<name>`): the `workers:` keys of
    workers.yaml, if the workspace has one. Independent of the agent role."""
    path = os.path.join(ROOT, "workers.yaml")
    if not os.path.exists(path):
        return []
    try:
        import yaml
        with open(path) as f:
            return list(((yaml.safe_load(f) or {}).get("workers") or {}).keys())
    except ImportError:  # no PyYAML: the two-space keys under `workers:`
        out, inside = [], False
        with open(path) as f:
            for line in f:
                if re.match(r"^\S", line):
                    inside = line.startswith("workers:")
                elif inside and (m := re.match(r"^  ([A-Za-z0-9_-]+):", line)):
                    out.append(m.group(1))
        return out


WORKERS = engines()
CARD = "<!-- card -->"  # marks a decision card comment (see core/MANUAL.md, "Decision card")
CARD_WORDS, CARD_BULLETS = 120, 5
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BODY = """## Goal

## Done when

## Plan

## Next
"""


def run(*args, check=True, input=None):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, input=input, timeout=60)
    if check and p.returncode != 0:
        raise SystemExit(f"{' '.join(args[:3])} failed: {p.stderr.strip() or p.stdout.strip()}")
    return p


def git(*args, check=True):
    return run("git", *args, check=check)


def repo():
    """owner/name of the home repo (origin)."""
    url = git("remote", "get-url", "origin").stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise SystemExit(f"origin is not a GitHub repo: {url}")
    return m.group(1)


def task_entries():
    """{name: (owner/repo, pickup)} for the repos.yaml entries marked `tasks: true` (pickup "all")
    or `tasks: assigned` (pickup "assigned"): the task repos besides home."""
    path = os.path.join(ROOT, "repos.yaml")
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path) as f:
            entries = (yaml.safe_load(f) or {}).get("repos") or {}
    except ImportError:  # no PyYAML: read the two fields we need from the flat two-level layout
        entries, cur = {}, None
        with open(path) as f:
            lines = f.readlines()
        for line in lines:
            m = re.match(r"^  ([A-Za-z0-9._-]+):\s*$", line)
            if m:
                cur = entries.setdefault(m.group(1), {})
                continue
            m = re.match(r"^    (remote|tasks):\s*(\S+)", line)
            if m and cur is not None:
                cur[m.group(1)] = {"true": True, "false": False}.get(m.group(2), m.group(2)) if m.group(1) == "tasks" else m.group(2)
    out = {}
    for name, e in entries.items():
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", str((e or {}).get("remote", "")))
        mode = {True: "all", "assigned": "assigned"}.get((e or {}).get("tasks"))
        if mode and m:
            out[name] = (m.group(1), mode)
    return out


def registry():
    """{name: owner/repo} of the task repos besides home."""
    return {name: r for name, (r, _) in task_entries().items()}


def pickup(r):
    """Which unassigned issues of task repo r (None = home) are the owner's: "all", or "assigned"
    (a shared repo, where an issue is someone's only once it is assigned)."""
    return "all" if r is None else task_entries().get(r, (None, "all"))[1]


_ME = []


def me():
    """The owner's GitHub login (workspace.yaml `github`, else the signed-in gh user), lowercase."""
    if not _ME:
        login = os.environ.get("TASK_OWNER") or ""
        if not login:
            sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
            import workspace
            login = str(workspace.get(ROOT, "github") or "")
        if not login:
            login = run("gh", "api", "user", "--jq", ".login", check=False).stdout.strip()
        _ME.append(login.lower())
    return _ME[0]


def assignees(issue):
    """Logins the issue is assigned to (lowercase); empty = unassigned."""
    return [a["login"].lower() for a in issue.get("assignees") or [] if a and a.get("login")]


def mine(issue):
    """Is the issue the owner's? Assigned to them, or unassigned outside a `tasks: assigned` repo.
    An issue assigned to someone else is theirs: their agents work on it, never ours."""
    a = assignees(issue)
    return me() in a if a else pickup(issue.get("_repo")) == "all"


def task_repos():
    """Repo names in queue order: None (home) first, then the other task repos."""
    return [None] + sorted(registry())


def full(r):
    """owner/name of task repo `r` (None = home)."""
    if r is None:
        return repo()
    reg = registry()
    if r not in reg:
        raise SystemExit(f"{r} is not a task repo (repos.yaml: tasks: true / assigned)")
    return reg[r]


def remote(r):
    """What git fetches/pushes claims and cards for repo `r` from: origin for home, the HTTPS URL otherwise."""
    return "origin" if r is None else f"https://github.com/{full(r)}.git"


def tracking(r):
    """Local ref prefix that mirrors repo `r`'s branches."""
    return "refs/remotes/origin" if r is None else f"refs/remotes/tasks/{r}"


def key(r, n=None):
    """Task key: the number for a home issue, "<repo>#<n>" for another task repo. Also takes an issue dict."""
    if isinstance(r, dict):
        r, n = r.get("_repo"), r["number"]
    return int(n) if r is None else f"{r}#{int(n)}"


def split(k):
    """(repo, number) of a task key; repo None = home."""
    if isinstance(k, int):
        return None, k
    r, n = k.rsplit("#", 1)
    return r, int(n)


def ref(k):
    """How a task is written for people: #81 or app#81."""
    r, n = split(k)
    return f"#{n}" if r is None else f"{r}#{n}"


def arg(k):
    """How a task is passed on a command line: 81 or app#81."""
    return str(k)


def parse_ref(text):
    """Task key from `81`, `#81`, `<repo>#81` or `<owner>/<repo>#81`."""
    m = re.fullmatch(r"\s*(?:([A-Za-z0-9._/-]+)?#)?(\d+)\s*", str(text))
    if not m:
        raise SystemExit(f"not a task ref: {text!r} (use 81 or <repo>#81)")
    name, n = m.group(1), int(m.group(2))
    if n < 1:
        raise SystemExit(f"not a task ref: {text!r}")
    if not name:
        return n
    reg = registry()
    if name in reg:
        return key(name, n)
    by_full = {v.lower(): k for k, v in reg.items()}
    if name.lower() in by_full:
        return key(by_full[name.lower()], n)
    home = repo()
    if name.lower() in (home.lower(), home.split("/")[1].lower()):
        return n
    raise SystemExit(f"{name} is not a task repo (repos.yaml: tasks: true / assigned)")


def api(path, method="GET", data=None, paginate=False, repo_name=None):
    args = ["gh", "api", "-X", method, f"repos/{full(repo_name)}/{path}"]
    if paginate:
        args += ["--paginate", "--jq", ".[]"]  # one JSON object per line across all pages
    if data is not None:
        args += ["--input", "-"]
    out = run(*args, input=None if data is None else json.dumps(data)).stdout
    if paginate:
        return [json.loads(line) for line in out.splitlines() if line.strip()]
    return json.loads(out) if out.strip() else None


def iapi(k, sub="", method="GET", data=None):
    """REST call on task k's issue (sub: e.g. "/comments"). A returned issue is tagged with its repo."""
    r, n = split(k)
    out = api(f"issues/{n}{sub}", method, data, repo_name=r) if r else api(f"issues/{n}{sub}", method, data)
    if not sub and isinstance(out, dict):
        out["_repo"] = r
    return out


def issues():
    """Open issues of every task repo, each tagged with `_repo` (None = home)."""
    res = []
    for r in task_repos():
        out = api("issues?state=open&per_page=100", paginate=True, repo_name=r) if r else api("issues?state=open&per_page=100", paginate=True)
        for i in out:
            if "pull_request" not in i:
                i["_repo"] = r
                res.append(i)
    return res


def labels(issue):
    return {l["name"] for l in issue["labels"]}


def prio(issue):
    for p in ("1", "2", "3"):
        if f"p{p}" in labels(issue):
            return int(p)
    return 2


def field(issue, name):
    m = re.search(rf"(?m)^{name}:\s*(.+?)\s*$", issue.get("body") or "")
    return m.group(1) if m else ""


def claims():
    """{task key: (tip_sha, verb, who, age_hours)} for every claim branch of every task repo."""
    now = datetime.datetime.now().timestamp()
    res = {}
    for r in task_repos():
        local = tracking(r)
        # Never make pickup/takeover decisions from a stale cache after a failed fetch.
        git("fetch", "--quiet", "--prune", remote(r), f"+refs/heads/{PREFIX}*:{local}/{PREFIX}*")
        out = git("for-each-ref", f"--format=%(refname:lstrip={local.count('/') + 2})%09%(objectname)%09%(committerdate:unix)%09%(contents:subject)",
                  f"{local}/{PREFIX}").stdout
        for line in out.splitlines():
            name, sha, ts, subject = line.split("\t", 3)
            m = re.match(r"(claim|release) #\d+ by (\S+)", subject)
            if name.isdigit() and m:
                res[key(r, name)] = (sha, m.group(1), m.group(2), (now - int(ts)) / 3600)
    return res


def workstreams(issue):
    """The issue's `ws:` labels, plus the workstream its repo stands for (a task repo's name) outside home."""
    ws = [l[3:] for l in labels(issue) if l.startswith("ws:")]
    r = issue.get("_repo")
    return ws + [r.lower()] if r and r.lower() not in ws else ws


def agent(issue):
    found = [a for a in AGENTS if f"agent:{a}" in labels(issue)]
    return found[0] if found else "dev"


def status(issue, c):
    """The issue's status label. An issue without one (e.g. made in the GitHub UI) counts as ready."""
    found = [st for st in OPEN if st in labels(issue)]
    return found[0] if found else "ready"


def claimed(n, c):
    return n in c and c[n][1] == "claim"


def active_claim(n, c):
    """Claims are leases: after two hours without refresh, another worker may take over."""
    return claimed(n, c) and c[n][3] <= STALE_HOURS


def by_prio(xs):
    xs = list(xs)
    order = {r: x for x, r in enumerate(task_repos())} if any(i.get("_repo") for i in xs) else {None: 0}
    return sorted(xs, key=lambda i: (prio(i), order.get(i.get("_repo"), 99), i["number"]))


def candidates(all_issues, c, who="dev"):
    """The owner's ready issues with no active claim, including expired leases, in pick-up order."""
    return by_prio(i for i in all_issues if not active_claim(key(i), c) and status(i, c) == "ready" and agent(i) == who and mine(i))


def due_holds(all_issues, c, who="dev"):
    """The owner's on-hold issues without active leases whose condition is due for a re-check."""
    today = datetime.date.today().isoformat()
    return by_prio(i for i in all_issues if not active_claim(key(i), c) and status(i, c) == "on-hold" and agent(i) == who
                   and mine(i) and (field(i, "Check after") or today) <= today)


def set_status(issue, st, waiting_on=None, check_after=None, keep_body=False):
    """Swap the status label (closing or reopening as needed) and rewrite the Waiting on / Check after lines."""
    old = issue.get("body") or ""
    body = old
    if not keep_body:
        body = re.sub(r"(?m)^(Waiting on|Check after):.*\n?", "", old).lstrip("\n")
        if waiting_on:
            body = f"Waiting on: {waiting_on}\n" + (f"Check after: {check_after}\n" if check_after else "") + "\n" + body
    names = labels(issue) - set(OPEN)
    patch = {}
    if st in ("done", "dropped"):
        if issue["state"] == "open":
            patch.update(state="closed", state_reason="completed" if st == "done" else "not_planned")
    else:
        names.add(st)
        if issue["state"] == "closed":
            patch["state"] = "open"
    if body != old or names != labels(issue) or patch:
        iapi(key(issue), "", "PATCH", {"body": body, "labels": sorted(names), **patch})


def read_card(path):
    """Check a decision card (a slide for the owner) and return (question, text). Exits with the reason if it's not one."""
    text = (sys.stdin.read() if path == "-" else open(path).read()).strip()
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].startswith("### "):
        raise SystemExit("card: the first line must be the question, as `### <question>`")
    words = len(re.sub(r"\]\([^)]*\)|https?://\S+|[#*`>|_-]", " ", text).split())
    bullets = sum(1 for l in lines if re.match(r"\s*[-*] ", l))
    if words > CARD_WORDS or bullets > CARD_BULLETS:
        raise SystemExit(f"card: {words} words / {bullets} bullets, max {CARD_WORDS} / {CARD_BULLETS}. "
                         "It's a slide: keep only what the decision needs, link the rest")
    return lines[0][4:].strip(), text


def post_card(k, text):
    iapi(k, "/comments", "POST", {"body": f"{CARD}\n{text}"})


CARDS = "cards"  # branch of each task repo holding its card images, one folder per issue


def cmd_upload(a):
    """Add files to branch `cards` of the task's repo under <n>/ (a new commit on top of the tip, retried on a race) and print their URLs."""
    import tempfile
    r, n = split(a.number)
    local = f"{tracking(r)}/{CARDS}"
    for attempt in range(5):
        git("fetch", "--quiet", remote(r), f"+refs/heads/{CARDS}:{local}", check=False)
        tip = git("rev-parse", "--verify", "--quiet", local, check=False).stdout.strip()
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
            def g(*args):
                p = subprocess.run(["git", *args], cwd=ROOT, env=env, text=True, capture_output=True)
                if p.returncode:
                    raise SystemExit(f"git {args[0]} failed: {p.stderr.strip()}")
                return p.stdout.strip()
            if tip:
                g("read-tree", tip)
            paths = []
            for f in a.files:
                blob = g("hash-object", "-w", f)
                paths.append(f"{n}/{os.path.basename(f)}")
                g("update-index", "--add", "--cacheinfo", f"100644,{blob},{paths[-1]}")
            tree = g("write-tree")
            sha = g("commit-tree", tree, *(["-p", tip] if tip else []), "-m", f"card images for #{n}")
        if git("push", "--quiet", remote(r), f"{sha}:refs/heads/{CARDS}", check=False).returncode == 0:
            for p in paths:
                print(f"https://github.com/{full(r)}/raw/{CARDS}/{p}")
            return
    raise SystemExit("could not push to the cards branch (kept racing); retry")


def push_state(k, verb, who, parent):
    """Push a `verb` commit on claim/<n> of the task's repo on top of parent (None = new branch). False if someone else moved it."""
    r, n = split(k)
    env_args = ["commit-tree", EMPTY_TREE, "-m", f"{verb} #{n} by {who}"]
    if parent:
        env_args[2:2] = ["-p", parent]
    sha = git(*env_args).stdout.strip()
    return git("push", "--quiet", remote(r), f"{sha}:refs/heads/{PREFIX}{n}", check=False).returncode == 0


def default_who():
    return os.environ.get("AGENT_CLAIM_ID") or f"{getpass.getuser()}@{socket.gethostname().split('.')[0]}#{uuid.uuid4().hex[:6]}"


def assignment_guard(n, who=None, issue=None, require_claim=False):
    """An assigned agent chooses when to claim, but cannot claim/edit another task."""
    expected = os.environ.get("AGENT_TASK_NUMBER")
    owner = os.environ.get("AGENT_CLAIM_ID")
    worker = os.environ.get("AGENT_WORKER")
    if not (expected and owner and worker):
        return
    if parse_ref(expected) != n or (who is not None and who != owner):
        raise SystemExit("use only the assigned issue and AGENT_CLAIM_ID")
    if issue is not None:
        pins = [l[7:] for l in labels(issue) if l.startswith("worker:")]
        ws = os.environ.get("AGENT_WORKSTREAM")
        if (issue["state"] != "open" or status(issue, {}) != "ready" or agent(issue) != "dev" or not mine(issue)
                or (pins and pins != [worker]) or (ws and not set(ws.split(",")) <= set(workstreams(issue)))):
            raise SystemExit("assigned issue is no longer ready for this worker; do not change it")
    if require_claim:
        current = claims()
        if not active_claim(n, current) or current[n][2] != owner:
            raise SystemExit("claim the assigned issue before changing it; ownership is not current")


def try_claim(n, who, steal=False):
    # --steal remains accepted for compatibility; expired leases are always reclaimable.
    # Re-read the remote tip here, not only when listing candidates: a worker may
    # have refreshed or claimed it in the meantime. push_state keeps the CAS race-safe.
    c = claims()
    tip = c.get(n)
    if tip and tip[1] == "claim" and tip[2] != who:
        if active_claim(n, c):
            return f"already claimed by {tip[2]} {tip[3]:.1f}h ago"
    if not push_state(n, "claim", who, tip[0] if tip else None):
        return "lost the race: someone else claimed it just now"
    return None


def cmd_list(_):
    c = claims()
    for i in sorted(issues(), key=lambda i: (OPEN.index(status(i, c)), prio(i), i["number"])):
        n, s = key(i), status(i, c)
        notes = []
        if s in NEEDS_NOTE:
            ca = field(i, "Check after")
            notes.append(f"on {field(i, 'Waiting on') or '?'}" + (f", check {ca}" if ca else ""))
        if claimed(n, c):
            notes.append(f"{'STALE ' if c[n][3] > STALE_HOURS else ''}claimed by {c[n][2]}, {c[n][3]:.1f}h ago")
        tags = " ".join(sorted(labels(i) - set(OPEN) - {"p1", "p2", "p3"})
                        + [f"@{x}" for x in assignees(i)] + ([] if assignees(i) or mine(i) else ["unassigned"]))
        print(f"{ref(n):<5} {s:13} p{prio(i)}  {i['title']}" + (f"  [{tags}]" if tags else "") + (f"  ({'; '.join(notes)})" if notes else ""))


def cmd_next(a):
    c = [i for i in candidates(issues(), claims(), a.agent) if not a.ws or a.ws in workstreams(i)]
    if not c:
        print("nothing to pick up")
        return
    for i in c if a.all else c[:1]:
        print(f"{key(i)}\t{i['title']}")


def cmd_holds(a):
    for i in due_holds(issues(), claims(), a.agent):
        if not a.ws or a.ws in workstreams(i):
            print(f"{key(i)}\t{i['title']}\t{field(i, 'Waiting on') or '?'}")


def cmd_take(a):
    if os.environ.get("AGENT_TASK_NUMBER") and os.environ.get("AGENT_WORKER"):
        raise SystemExit("assigned worker: use claim <AGENT_TASK_NUMBER>; do not select a different task")
    who = a.who or default_who()
    for i in candidates(issues(), claims(), a.agent):
        if try_claim(key(i), who) is None:
            print(f"{key(i)}\t{who}\t{i['title']}")
            return
    raise SystemExit("nothing to pick up")


def cmd_claim(a):
    who = a.who or default_who()
    issue = iapi(a.number)
    assignment_guard(a.number, who, issue)
    if issue["state"] != "open":
        raise SystemExit(f"{ref(a.number)} is {issue['state']}")
    err = try_claim(a.number, who, a.steal)
    if err:
        raise SystemExit(err)
    if os.environ.get("AGENT_TASK_NUMBER") and os.environ.get("AGENT_WORKER"):
        try:
            assignment_guard(a.number, who, iapi(a.number))
        except BaseException:
            # A person may have paused/rerouted the issue during the push. Release
            # only this worker's new lease, without rewriting that person's status.
            tip = claims().get(a.number)
            if tip and tip[1:3] == ("claim", who):
                push_state(a.number, "release", who, tip[0])
            raise
        run_dir = os.environ.get("AGENT_RUN_DIR")
        if run_dir:
            marker = Path(run_dir) / "claim.json"
            pending = marker.with_suffix(f".{os.getpid()}.tmp")
            pending.write_text(json.dumps({"issue": a.number, "owner": who}) + "\n")
            pending.replace(marker)
    if status(issue, {}) != "ready":  # whoever holds the claim is the agent working on it
        set_status(issue, "ready")
    print(who)


def cmd_release(a):
    assignment_guard(a.number, a.who, require_claim=True)
    tip = claims().get(a.number)
    if not tip or tip[1] != "claim":
        raise SystemExit(f"{ref(a.number)} is not claimed")
    expected_owner = a.who or (os.environ.get("AGENT_CLAIM_ID") if os.environ.get("AGENT_TASK_NUMBER") else None)
    if expected_owner and tip[2] != expected_owner:
        raise SystemExit(f"{ref(a.number)} is claimed by {tip[2]}, not {expected_owner}")
    issue = iapi(a.number)
    if a.card:
        post_card(a.number, a.card)
    set_status(issue, a.to or status(issue, {a.number: tip}), a.waiting_on, a.check_after)  # no --to: keep the status
    if not push_state(a.number, "release", tip[2], tip[0]):
        raise SystemExit("claim branch moved under us; run `task.sh list` and retry")
    print(f"released {ref(a.number)}")


def cmd_set(a):
    assignment_guard(a.number, require_claim=True)
    if a.card:
        post_card(a.number, a.card)
    set_status(iapi(a.number), a.status, a.waiting_on, a.check_after)
    print(f"{ref(a.number)} is {a.status}")


def cmd_new(a):
    """Create a task. --repo picks the task repo; without it, a --ws naming a task repo files it there."""
    reg = registry()
    r = a.repo
    if r is None:
        r = next((name for w in a.ws for name in reg if name.lower() == w.lower()), None)
    elif r not in reg:
        r = split(parse_ref(f"{r}#1"))[0]  # accepts owner/name and the home repo's name
    ws = [w for w in a.ws if not r or w.lower() != r.lower()]  # the repo already says it
    if a.worker:
        ensure_worker_labels(r)
    owners = getattr(a, "assignee", None) or ([me()] if pickup(r) == "assigned" else [])  # a shared repo: the owner's unless told otherwise
    data = {"title": a.title, "body": BODY, **({"assignees": owners} if owners else {}),
            "labels": ["backlog" if a.backlog else "ready", f"p{a.priority}"] + [f"ws:{w}" for w in ws]
            + ([f"agent:{a.agent}"] if a.agent != "dev" else [])
            + ([f"worker:{a.worker}"] if a.worker else [])}
    out = api("issues", "POST", data, repo_name=r) if r else api("issues", "POST", data)
    print(key(r, out["number"]))


def cmd_assign(a):
    """Hand an issue to another agent: swap its agent:<name> label (dev = no label)."""
    issue = iapi(a.number)
    names = {l for l in labels(issue) if not l.startswith("agent:")} | ({f"agent:{a.agent}"} if a.agent != "dev" else set())
    if names != labels(issue):
        iapi(a.number, "", "PATCH", {"labels": sorted(names)})
    print(f"{ref(a.number)} is for {a.agent}")


def cmd_assignee(a):
    """Give an issue to a person (its GitHub assignee): `me`, a login, or `none` (unassigned)."""
    issue = iapi(a.number)
    login = {"me": me(), "none": ""}.get(a.login, a.login)
    current = [x["login"] for x in issue.get("assignees") or []]
    if current:
        iapi(a.number, "/assignees", "DELETE", {"assignees": current})
    if login:
        out = iapi(a.number, "/assignees", "POST", {"assignees": [login]})
        if login.lower() not in [x["login"].lower() for x in out.get("assignees") or []]:
            raise SystemExit(f"GitHub did not assign {login} (not a collaborator on {full(split(a.number)[0])}?)")
    print(f"{ref(a.number)} belongs to {('@' + login) if login else 'nobody (unassigned)'}")


def cmd_worker(a):
    """Pin an engine, or restore automatic routing, without changing role/status."""
    issue = iapi(a.number)
    if a.worker != "auto":
        ensure_worker_labels(split(a.number)[0])
    names = {l for l in labels(issue) if not l.startswith("worker:")}
    if a.worker != "auto":
        names.add(f"worker:{a.worker}")
    if names != labels(issue):
        iapi(a.number, "", "PATCH", {"labels": sorted(names)})
    print(f"{ref(a.number)}: worker={a.worker}")


# The labels of the task system (core/MANUAL.md, "Tasks"); `setup <repo>` creates the missing ones.
LABELS = {
    "in-review": ("d93f0b", "Someone's turn (the assignee, else the owner): a decision card waits for an answer"),
    "ready": ("1d76db", "Agent's turn"),
    "on-hold": ("fbca04", "Waits for a condition (Waiting on:)"),
    "backlog": ("cfd3d7", "Idea or not specified yet; agents don't pick it up"),
    "p1": ("b60205", "Priority 1 (highest)"),
    "p2": ("fbca04", "Priority 2 (default)"),
    "p3": ("c5def5", "Priority 3"),
    "agent:pm": ("ededed", "For the product-manager agent"),
    **{f"worker:{w}": ("5319e7", f"Strict execution engine: {w}; no automatic fallback") for w in WORKERS},
}


def ensure_labels(r=None, names=None):
    """Initialize task-system labels in repo r through REST; preserve existing label metadata."""
    kw = {"repo_name": r} if r else {}
    existing = {l["name"] for l in api("labels?per_page=100", paginate=True, **kw)}
    for name in names or LABELS:
        if name not in existing:
            color, desc = LABELS[name]
            api("labels", "POST", {"name": name, "color": color, "description": desc}, **kw)
            print(f"created label {name}", file=sys.stderr)


def ensure_worker_labels(r=None):
    """Initialize routing tags through REST; preserve existing label metadata."""
    ensure_labels(r, [f"worker:{w}" for w in WORKERS])


def cmd_setup(a):
    r = None if a.repo is None else split(parse_ref(f"{a.repo}#1"))[0]
    ensure_labels(r)
    print(f"labels ready in {full(r)}")


def cmd_prune(_):
    c = claims()
    for k in sorted(c, key=str):
        r, n = split(k)
        if iapi(k)["state"] == "closed":
            ok = git("push", "--quiet", remote(r), f":refs/heads/{PREFIX}{n}", check=False).returncode == 0
            print(f"{'deleted' if ok else 'could not delete'} {PREFIX}{n} in {full(r)}")


def main():
    p = argparse.ArgumentParser(prog="task.sh")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    h = sub.add_parser("holds"); h.add_argument("--ws"); h.set_defaults(fn=cmd_holds)
    nx = sub.add_parser("next"); nx.add_argument("--all", action="store_true"); nx.add_argument("--ws"); nx.set_defaults(fn=cmd_next)
    t = sub.add_parser("take"); t.add_argument("--as", dest="who"); t.set_defaults(fn=cmd_take)
    for x in (h, nx, t):
        x.add_argument("--agent", choices=AGENTS, default="dev", help="whose queue (default dev)")
    n = sub.add_parser("new"); n.add_argument("title")
    n.add_argument("--priority", type=int, choices=[1, 2, 3], default=2)
    n.add_argument("--ws", action="append", default=[]); n.add_argument("--backlog", action="store_true")
    n.add_argument("--agent", choices=AGENTS, default="dev")
    n.add_argument("--worker", choices=WORKERS, help="strict engine pin; omitted = automatic")
    n.add_argument("--repo", help="task repo (repos.yaml name); default: the task repo a --ws names, else home")
    n.add_argument("--assignee", action="append", default=[], help="whose task (GitHub login); default: the owner in a `tasks: assigned` repo, else nobody")
    n.set_defaults(fn=cmd_new)
    c = sub.add_parser("claim"); c.add_argument("number", type=parse_ref); c.add_argument("--as", dest="who")
    c.add_argument("--steal", action="store_true", help="compatibility flag; stale claims are reclaimed automatically"); c.set_defaults(fn=cmd_claim)
    r = sub.add_parser("release"); r.add_argument("number", type=parse_ref); r.add_argument("--as", dest="who")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--to", choices=STATUSES)
    g.add_argument("--done", dest="to", action="store_const", const="done")
    g.add_argument("--dropped", dest="to", action="store_const", const="dropped")
    r.set_defaults(fn=cmd_release)
    st = sub.add_parser("set"); st.add_argument("number", type=parse_ref); st.add_argument("status", choices=STATUSES)
    st.set_defaults(fn=cmd_set)
    for x in (r, st):
        x.add_argument("--waiting-on"); x.add_argument("--check-after")
        x.add_argument("--card", help="decision card file (- = stdin), required with in-review")
    asg = sub.add_parser("assign"); asg.add_argument("number", type=parse_ref); asg.add_argument("agent", choices=AGENTS)
    asg.set_defaults(fn=cmd_assign)
    ow = sub.add_parser("assignee", help="whose task it is: me, a GitHub login, or none")
    ow.add_argument("number", type=parse_ref); ow.add_argument("login"); ow.set_defaults(fn=cmd_assignee)
    w = sub.add_parser("worker"); w.add_argument("number", type=parse_ref); w.add_argument("worker", choices=WORKERS + ["auto"])
    w.set_defaults(fn=cmd_worker)
    sub.add_parser("prune").set_defaults(fn=cmd_prune)
    su = sub.add_parser("setup", help="create the task-system labels in a task repo")
    su.add_argument("repo", nargs="?"); su.set_defaults(fn=cmd_setup)
    up = sub.add_parser("upload"); up.add_argument("number", type=parse_ref); up.add_argument("files", nargs="+")
    up.set_defaults(fn=cmd_upload)
    a = p.parse_args()
    if a.cmd in ("release", "set"):
        if a.cmd == "release" and not a.to and a.check_after:
            a.to = "on-hold"
        s = a.to if a.cmd == "release" else a.status
        if s == "in-review":
            if not a.card:
                p.error("in-review needs --card (the decision card, see core/MANUAL.md)")
            question, a.card = read_card(a.card)
            a.waiting_on = a.waiting_on or question
        elif a.card:
            p.error("--card goes with in-review only")
        if s == "on-hold" and not a.waiting_on:
            p.error("on-hold needs --waiting-on (the condition to wait for)")
        if (a.waiting_on and s not in NEEDS_NOTE) or (a.check_after and s != "on-hold"):
            p.error("--waiting-on goes with in-review or on-hold, --check-after with on-hold only")
    a.fn(a)


if __name__ == "__main__":
    main()

