from research.paper_h import contribution, gitlog

RS, US, GS = gitlog.RS, gitlog.US, gitlog.GS


def _record(sha, parents, date, cname, subject, trailers, body):
    return RS + US.join([sha, parents, date, cname, subject, GS.join(trailers), body])


def test_parse_log_reads_trailers_merges_and_committer_without_email():
    text = (_record("a" * 40, "", "2026-01-02", "Owner", "first",
                    ["Claude Opus 4.8 <noreply@anthropic.com>"], "first\n\nCo-Authored-By: ...")
            + _record("b" * 40, "a" * 40 + " " + "c" * 40, "2026-02-03", "GitHub", "Merge PR #1", [], "Merge"))
    cs = gitlog.parse_log(text)
    assert [c.sha[0] for c in cs] == ["a", "b"]
    assert cs[0].is_agent and gitlog.model_label(cs[0].agent_trailer) == "Claude Opus 4.8"
    assert not cs[1].is_agent and cs[1].is_merge and cs[1].committer == "GitHub"
    assert cs[0].committer == "local" and cs[0].month == "2026-01"


def test_agent_coauthor_predicate():
    assert gitlog.is_agent_coauthor("Claude <noreply@anthropic.com>")
    assert gitlog.is_agent_coauthor("Claude Opus 5.5 (1M context) <noreply@anthropic.com>")
    assert not gitlog.is_agent_coauthor("Jane Doe <jane@example.org>")


def test_parse_numstat_handles_binary_and_tabs_in_paths():
    text = RS + "abc\n10\t2\tsrc/a.py\n-\t-\tbin/x.exe\n" + RS + "def\n0\t5\tdocs/iec62304/x.md\n"
    s = gitlog.parse_numstat(text)
    assert s["abc"] == [(10, 2, "src/a.py"), (None, None, "bin/x.exe")]
    assert gitlog.touched(s["def"], ("docs/iec62304/",))
    assert not gitlog.touched(s["abc"], ("docs/",))


def test_log_and_counts_on_a_real_tiny_repository(tiny_repo):
    cs = gitlog.log(tiny_repo, "main")
    assert len(cs) == 4
    counts = contribution.commit_counts(cs)
    assert counts["all"] == {"total": 4, "agent": 2, "share": 0.5}
    assert counts["merges"] == {"total": 1, "agent": 1}
    monthly = contribution.monthly(cs)
    assert monthly["2026-01"]["agent"] == 1 and monthly["2026-02"]["total"] == 3
    stats = gitlog.numstat(tiny_repo, "main")
    assert contribution.touching(cs, stats, ("docs/",)) == {"commits": 1, "agent": 1, "share": 1.0}
    lines = contribution.lines(cs, stats)
    assert lines["initial_commit"]["agent_trailer"] is True
    assert lines["excluding_initial_commit"]["agent"]["commits"] == 0   # merge excluded, root excluded
