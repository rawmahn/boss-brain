"""Queue lease regressions. Run: python3 -m unittest discover -s scripts -p 'test_*.py'."""
import contextlib
import datetime
import io
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import task


def issue(n, *labels):
    return {"number": n, "title": f"task {n}", "state": "open", "body": "",
            "labels": [{"name": s} for s in labels]}


def lease(age, who="old-worker", verb="claim"):
    return ("old-tip", verb, who, age)


class QueueTests(unittest.TestCase):
    def test_ready_queue_includes_expired_claims_but_not_fresh_claims(self):
        xs = [issue(49, "ready"), issue(70, "ready"), issue(71, "ready")]
        self.assertEqual([i["number"] for i in task.candidates(xs, {49: lease(35), 70: lease(19), 71: lease(1)})], [49, 70])

    def test_two_hour_boundary_priority_and_agent_filters(self):
        xs = [issue(1, "ready"), issue(2, "ready", "p1"), issue(3, "ready", "agent:pm"), issue(4, "backlog")]
        self.assertEqual([i["number"] for i in task.candidates(xs, {1: lease(2)})], [2])
        self.assertEqual([i["number"] for i in task.candidates(xs, {1: lease(2.001)})], [2, 1])
        self.assertEqual([i["number"] for i in task.candidates(xs, {}, "pm")], [3])

    def test_released_and_unlabelled_issues_remain_pickable(self):
        self.assertEqual([i["number"] for i in task.candidates([issue(1), issue(2, "ready")], {2: lease(1, verb="release")})], [1, 2])

    def test_next_workstream_query_is_read_only_and_shows_expired_claim(self):
        xs = [issue(49, "ready", "ws:app"), issue(50, "ready", "ws:web")]
        args = types.SimpleNamespace(agent="dev", ws="app", all=True)
        out = io.StringIO()
        with patch.object(task, "issues", return_value=xs), patch.object(task, "claims", return_value={49: lease(35)}), patch.object(task, "push_state") as push, contextlib.redirect_stdout(out):
            task.cmd_next(args)
        self.assertEqual(out.getvalue(), "49\ttask 49\n")
        push.assert_not_called()

    def test_due_holds_recover_expired_claims_and_respect_dates(self):
        xs = [issue(1, "on-hold"), issue(2, "on-hold"), issue(3, "on-hold")]
        xs[2]["body"] = "Check after: " + str(datetime.date.today() + datetime.timedelta(days=1))
        self.assertEqual([i["number"] for i in task.due_holds(xs, {1: lease(7), 2: lease(1)})], [1])

    def test_claim_recovers_expired_lease_without_steal_flag(self):
        with patch.object(task, "claims", return_value={49: lease(35)}), patch.object(task, "push_state", return_value=True) as push:
            self.assertIsNone(task.try_claim(49, "new-worker"))
        push.assert_called_once_with(49, "claim", "new-worker", "old-tip")

    def test_fresh_claim_is_protected_even_with_steal(self):
        with patch.object(task, "claims", return_value={49: lease(2)}), patch.object(task, "push_state") as push:
            self.assertIn("already claimed", task.try_claim(49, "new-worker", steal=True))
        push.assert_not_called()

    def test_own_claim_refresh_remains_possible(self):
        with patch.object(task, "claims", return_value={49: lease(1, who="worker")}), patch.object(task, "push_state", return_value=True) as push:
            self.assertIsNone(task.try_claim(49, "worker"))
        push.assert_called_once()

    def test_refreshed_claim_between_query_and_take_is_not_stolen(self):
        snapshots = [{49: lease(35)}, {49: lease(0)}]
        args = types.SimpleNamespace(agent="dev", who="new-worker")
        with patch.object(task, "issues", return_value=[issue(49, "ready")]), patch.object(task, "claims", side_effect=snapshots), patch.object(task, "push_state") as push:
            with self.assertRaisesRegex(SystemExit, "nothing to pick up"):
                task.cmd_take(args)
        push.assert_not_called()

    def test_take_recovers_expired_lease(self):
        args = types.SimpleNamespace(agent="dev", who="new-worker")
        out = io.StringIO()
        with patch.object(task, "issues", return_value=[issue(49, "ready")]), patch.object(task, "claims", return_value={49: lease(35)}), patch.object(task, "push_state", return_value=True) as push, contextlib.redirect_stdout(out):
            task.cmd_take(args)
        self.assertEqual(out.getvalue(), "49\tnew-worker\ttask 49\n")
        push.assert_called_once_with(49, "claim", "new-worker", "old-tip")

    def test_old_owner_cannot_release_successor_claim(self):
        args = types.SimpleNamespace(number=49, who="old-worker")
        with patch.object(task, "claims", return_value={49: lease(0, who="new-worker")}), patch.object(task, "api") as api:
            with self.assertRaisesRegex(SystemExit, "not old-worker"):
                task.cmd_release(args)
        api.assert_not_called()

    def test_failed_fetch_stops_before_using_cached_claims(self):
        with patch.object(task, "git", side_effect=SystemExit("fetch failed")) as git:
            with self.assertRaisesRegex(SystemExit, "fetch failed"):
                task.claims()
        self.assertNotIn("check", git.call_args.kwargs)


class GitRaceTests(unittest.TestCase):
    def test_two_takeovers_of_same_tip_have_only_one_winner(self):
        with tempfile.TemporaryDirectory() as d:
            remote, a, b = [Path(d) / name for name in ("remote.git", "a", "b")]
            def git(*args):
                return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
            git("init", "--bare", remote)
            for root in (a, b):
                git("init", root)
                git("-C", root, "remote", "add", "origin", remote)
                git("-C", root, "config", "user.name", "Lease test")
                git("-C", root, "config", "user.email", "test@example.invalid")
                git("-C", root, "hash-object", "-t", "tree", "-w", "--stdin")
            with patch.object(task, "ROOT", str(a)):
                self.assertTrue(task.push_state(49, "claim", "old-worker", None))
                parent = task.claims()[49][0]
            with patch.object(task, "ROOT", str(b)):
                self.assertEqual(task.claims()[49][0], parent)
            with patch.object(task, "ROOT", str(a)):
                self.assertTrue(task.push_state(49, "claim", "winner", parent))
            with patch.object(task, "ROOT", str(b)):
                self.assertFalse(task.push_state(49, "claim", "loser", parent))
                self.assertEqual(task.claims()[49][2], "winner")


class MultiRepoTests(unittest.TestCase):
    """Tasks in other task repos: refs `<repo>#<n>`, state (claims, cards) in that repo."""

    def setUp(self):
        self.reg = patch.object(task, "registry", return_value={"app": "acme/app"})
        self.reg.start()
        self.addCleanup(self.reg.stop)
        self.home = patch.object(task, "repo", return_value="acme/workspace")
        self.home.start()
        self.addCleanup(self.home.stop)

    def test_refs_parse_to_keys_and_back(self):
        self.assertEqual(task.parse_ref("81"), 81)
        self.assertEqual(task.parse_ref("#81"), 81)
        self.assertEqual(task.parse_ref("workspace#81"), 81)
        self.assertEqual(task.parse_ref("app#81"), "app#81")
        self.assertEqual(task.parse_ref("acme/app#81"), "app#81")
        self.assertEqual(task.split("app#81"), ("app", 81))
        self.assertEqual((task.ref(81), task.ref("app#81")), ("#81", "app#81"))
        for bad in ("web#3", "x", "0"):
            with self.assertRaises(SystemExit):
                task.parse_ref(bad)

    def test_same_number_in_two_repos_are_different_tasks(self):
        xs = [dict(issue(5, "ready"), _repo=None), dict(issue(5, "ready", "p1"), _repo="app")]
        c = {5: lease(1)}  # only the home #5 is claimed
        self.assertEqual([task.key(i) for i in task.candidates(xs, c)], ["app#5"])

    def test_repo_stands_for_its_workstream(self):
        i = dict(issue(5, "ready"), _repo="app")
        self.assertEqual(task.workstreams(i), ["app"])
        self.assertEqual(task.workstreams(dict(issue(6, "ws:research"), _repo=None)), ["research"])

    def test_issue_calls_go_to_the_task_repo(self):
        with patch.object(task, "run") as run:
            run.return_value = types.SimpleNamespace(stdout='{"number": 7, "labels": []}')
            got = task.iapi("app#7")
        self.assertEqual(run.call_args.args[:5], ("gh", "api", "-X", "GET", "repos/acme/app/issues/7"))
        self.assertEqual(got["_repo"], "app")

    def test_new_with_task_repo_workstream_files_it_there_without_the_label(self):
        args = types.SimpleNamespace(title="t", ws=["app"], repo=None, backlog=False, priority=2, agent="dev", worker=None)
        with patch.object(task, "api", return_value={"number": 3}) as api, contextlib.redirect_stdout(io.StringIO()) as out:
            task.cmd_new(args)
        self.assertEqual(api.call_args.kwargs, {"repo_name": "app"})
        self.assertEqual(api.call_args.args[2]["labels"], ["ready", "p2"])
        self.assertEqual(out.getvalue(), "app#3\n")

    def test_assignee_decides_whose_task_it_is(self):
        def who(i, *logins):
            return dict(i, assignees=[{"login": x} for x in logins])
        xs = [who(dict(issue(1, "ready"), _repo=None)),                       # home, unassigned: mine
              who(dict(issue(2, "ready"), _repo=None), "Someone"),            # assigned to someone else
              who(dict(issue(3, "ready"), _repo="app")),                      # shared repo, unassigned: nobody's yet
              who(dict(issue(4, "ready"), _repo="app"), "Owner"),             # shared repo, assigned to me
              who(dict(issue(5, "on-hold"), _repo="app"))]
        with patch.object(task, "me", return_value="owner"), patch.object(task, "pickup", side_effect=lambda r: "assigned" if r else "all"):
            self.assertEqual([task.key(i) for i in task.candidates(xs, {})], [1, "app#4"])
            self.assertEqual(task.due_holds(xs, {}), [])
        with patch.object(task, "me", return_value="owner"), patch.object(task, "pickup", return_value="all"):
            self.assertEqual([task.key(i) for i in task.candidates(xs, {})], [1, "app#3", "app#4"])

    def test_tasks_assigned_marks_a_shared_repo(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "repos.yaml").write_text("repos:\n  app:\n    remote: https://github.com/acme/app.git\n    tasks: assigned\n"
                                             "  lib:\n    remote: https://github.com/acme/lib.git\n    tasks: true\n"
                                             "  web:\n    remote: https://github.com/acme/web.git\n")
            self.reg.stop()
            with patch.object(task, "ROOT", d):
                self.assertEqual(task.registry(), {"app": "acme/app", "lib": "acme/lib"})
                self.assertEqual((task.pickup("app"), task.pickup("lib"), task.pickup(None)), ("assigned", "all", "all"))
            self.reg.start()

    def test_new_in_a_shared_repo_assigns_the_owner(self):
        args = types.SimpleNamespace(title="t", ws=[], repo="app", backlog=False, priority=2, agent="dev", worker=None, assignee=[])
        with patch.object(task, "api", return_value={"number": 3}) as api, patch.object(task, "me", return_value="owner"), \
                patch.object(task, "pickup", return_value="assigned"), contextlib.redirect_stdout(io.StringIO()):
            task.cmd_new(args)
        self.assertEqual(api.call_args.args[2]["assignees"], ["owner"])

    def test_claims_live_in_each_task_repo(self):
        with tempfile.TemporaryDirectory() as d:
            home, other, work = [Path(d) / n for n in ("home.git", "other.git", "work")]
            def git(*args):
                return subprocess.run(["git", *map(str, args)], check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
            git("init", "--bare", home); git("init", "--bare", other); git("init", work)
            git("-C", work, "remote", "add", "origin", home)
            git("-C", work, "config", "user.name", "Lease test")
            git("-C", work, "config", "user.email", "test@example.invalid")
            git("-C", work, "hash-object", "-t", "tree", "-w", "--stdin")
            remotes = {None: "origin", "app": str(other)}
            with patch.object(task, "ROOT", str(work)), patch.object(task, "remote", side_effect=remotes.get):
                self.assertTrue(task.push_state(5, "claim", "a", None))
                self.assertTrue(task.push_state("app#5", "claim", "b", None))
                c = task.claims()
            self.assertEqual({k: v[2] for k, v in c.items()}, {5: "a", "app#5": "b"})
            self.assertEqual(git("--git-dir", other, "for-each-ref", "--format=%(refname)"), "refs/heads/claim/5")
            self.assertIn("claim #5 by b", git("--git-dir", other, "log", "-1", "--format=%s", "claim/5"))


if __name__ == "__main__":
    unittest.main()
