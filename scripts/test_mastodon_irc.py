#!/usr/bin/env python3
"""Tests for scripts/mastodon_irc.py, the WeeChat cross-posting script.

Run with: python3 scripts/test_mastodon_irc.py

The weechat module is replaced with a small recording fake before the
script is imported; feed downloads are driven against the committed
RSS fixture (via file:// URLs) by delivering them to the recorded
hook_process callback. Posting is asserted on the fake's recorded
weechat.command calls.
"""

import importlib
import json
import os
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

FIXTURE = os.path.join(SCRIPT_DIR, "fixtures", "mastodon-farmos.rss.xml")
BUFFER = "irc.oftc.#farmOS"


def make_fake_weechat():
    """Build a fake weechat module that records API calls.

    Signatures match the deployed WeeChat 4.x API: register takes
    seven strings, hook_timer/hook_process take the callback as a
    string naming a module-level function, and the return-code
    constants are OK=0 / OK_EAT=1 / ERROR=-1 and
    WEECHAT_HOOK_PROCESS_ERROR=-2.
    """
    fake = types.ModuleType("weechat")
    fake.WEECHAT_RC_OK = 0
    fake.WEECHAT_RC_OK_EAT = 1
    fake.WEECHAT_RC_ERROR = -1
    fake.WEECHAT_HOOK_PROCESS_ERROR = -2
    fake.registered = []   # weechat.register argument tuples
    fake.hooks = []        # weechat.hook_timer argument tuples
    fake.processes = []    # weechat.hook_process argument tuples
    fake.commands = []     # (buffer, line) pairs from weechat.command
    fake.prnts = []        # messages passed to weechat.prnt
    fake.info_values = {}  # name -> value for weechat.info_get

    def register(name, author, version, license, description,
                 shutdown_func, charset):
        fake.registered.append(
            (name, author, version, license, description,
             shutdown_func, charset)
        )

    def hook_timer(interval, align_second, max_calls, callback, data):
        fake.hooks.append((interval, align_second, max_calls, callback, data))
        return "hook"

    def hook_process(command, timeout, callback, data):
        fake.processes.append((command, timeout, callback, data))
        return "hook"

    def command(buffer, command_text):
        fake.commands.append((buffer, command_text))
        return fake.WEECHAT_RC_OK

    def prnt(buffer, message):
        fake.prnts.append(message)

    def info_get(name, arguments=""):
        return fake.info_values.get(name, "")

    fake.register = register
    fake.hook_timer = hook_timer
    fake.hook_process = hook_process
    fake.command = command
    fake.prnt = prnt
    fake.info_get = info_get
    return fake


def load_module(tmp, state_ids=None, feed="file://" + FIXTURE):
    """(Re)import the script against a fresh fake weechat module.

    WeeChat 4.x runs the script at load with no init callback, so the
    module-level setup (registration, timer, first fetch) runs during
    the import, with the environment overrides installed first.
    Returns (module, fake, state_path).
    """
    fake = make_fake_weechat()
    state_path = os.path.join(tmp, "state.json")
    if state_ids is not None:
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(list(state_ids), handle)
    os.environ["MASTODON_IRC_STATE_FILE"] = state_path
    os.environ["MASTODON_IRC_FEED_URL"] = feed
    sys.modules["weechat"] = fake
    sys.modules.pop("mastodon_irc", None)
    return importlib.import_module("mastodon_irc"), fake, state_path


def fetch_cycle(m, fake, feed="file://" + FIXTURE):
    """Deliver the latest feed download to the script's callback.

    Mirrors how weechat.hook_process delivers a URL transfer: once
    with the body (return_code < 0) and once to finish (return_code
    >= 0), or once with WEECHAT_HOOK_PROCESS_ERROR on failure.
    """
    command, timeout, callback, data = fake.processes[-1]
    assert command == f"url:{feed}"
    url = command[len("url:"):]
    func = getattr(m, callback)
    try:
        with open(url[len("file://"):], "rb") as handle:
            body = handle.read()
    except OSError:
        func(data, command, fake.WEECHAT_HOOK_PROCESS_ERROR, "", "curl error")
        return
    func(data, command, -1, body.decode("utf-8"), "")
    func(data, command, 0, "", "")


def buffer_handle(fake):
    """Mark the channel as joined in the fake; return its handle.

    Info "irc_buffer" resolves to the buffer pointer only while the
    channel is joined on the server; the default (not set) is "".
    """
    fake.info_values["irc_buffer"] = "buffer-handle"
    return "buffer-handle"


def make_feed(tmp, name, toots):
    """Write a minimal RSS feed file; toots are (html, status url)."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel><title>farmOS.org</title>',
    ]
    for html_body, status_url in toots:
        lines.append(
            f"<item><guid>{status_url}</guid><link>{status_url}</link>"
            f"<description><![CDATA[{html_body}]]></description></item>"
        )
    lines.append("</channel></rss>")
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return "file://" + path


def fixture_items():
    """Parse the committed RSS fixture directly; newest first."""
    channel = ET.parse(FIXTURE).getroot().find("channel")
    return [
        {
            "id": element.findtext("guid").rsplit("/", 1)[-1],
            "url": element.findtext("link").strip(),
            "html": "".join(element.find("description").itertext()).strip(),
        }
        for element in channel.findall("item")
    ]


def posted_line(m, item):
    """The /me line the script produces for a toot item."""
    return f"/me farmOS.org => {m.html_to_text(item['html'])} => {item['url']}"


def test_load():
    """The import registers the script, hooks a timer, and seeds state."""
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(tmp)
        # Registered with the WeeChat 4.x seven-string signature.
        name, author, version, license, description, shutdown, charset = (
            fake.registered[0]
        )
        assert name == "mastodon_irc"
        assert version == "1.0"
        assert description == (
            "Cross-post farmOS toots from fosstodon.org to #farmOS"
        )
        assert shutdown == "" and charset == "utf-8"
        # A recurring timer with a string callback.
        interval, align_second, max_calls, callback, data = fake.hooks[0]
        assert (align_second, max_calls, callback, data) == (
            0, 0, "on_tick", ""
        )
        assert interval == m.TICK_MS
        # The first feed download is a url: transfer via hook_process.
        command, timeout, callback, data = fake.processes[0]
        assert command == "url:file://" + FIXTURE
        assert timeout == m.FETCH_TIMEOUT_MS
        assert callback == "on_feed_fetched" and data == ""
        # The first run seeds the state without posting.
        fetch_cycle(m, fake)
        m.on_tick("", 0)
        assert fake.commands == []
        assert m.load_state() == [
            item["id"] for item in reversed(fixture_items())
        ]
        assert any("first run: seeded" in p for p in fake.prnts)


def test_html_to_text():
    with tempfile.TemporaryDirectory() as tmp:
        m, _fake, _ = load_module(tmp)
        # Mastodon splits long URLs into invisible/ellipsis spans;
        # the flat text must reconstruct the full URL.
        markup = (
            '<p>#farmOS 3.5.9 has been released! '
            '<a href="https://github.com/farmOS/farmOS/releases/3.5.9">'
            '<span class="invisible">https://</span>'
            '<span class="ellipsis">github.com/farmOS/farmOS/relea</span>'
            '<span class="invisible">ses/3.5.9</span></a></p>'
        )
        assert m.html_to_text(markup) == (
            "#farmOS 3.5.9 has been released! "
            "https://github.com/farmOS/farmOS/releases/3.5.9"
        )
        # Mentions flatten, entities decode, blocks and br become spaces.
        assert m.html_to_text(
            '<p>(thanks <span class="h-card">'
            '<a class="u-url mention">@<span>pcambra</span></a></span>!)</p>'
        ) == "(thanks @pcambra!)"
        assert m.html_to_text('<p>Called &quot;FarmOS&quot;.</p>') == (
            'Called "FarmOS".'
        )
        assert m.html_to_text("<p>a</p><p>b</p>") == "a b"
        assert m.html_to_text("line<br>two") == "line two"
        assert m.html_to_text("a\n  b\tc") == "a b c"


def test_parse_feed():
    with open(FIXTURE, "rb") as fixture_file:
        data = fixture_file.read()
    with tempfile.TemporaryDirectory() as tmp:
        m, _fake, _ = load_module(tmp)
        title, items = m.parse_feed(data)
    assert title == "farmOS.org"
    assert len(items) == 20
    # Newest first, with numeric snowflake ids and permalinks.
    assert items[0]["id"] == "117480766864583260"
    assert items[0]["url"] == (
        "https://fosstodon.org/@farmOS/117480766864583260"
    )
    assert items[-1]["id"] == "116772572816309676"
    assert all(item["id"].isdigit() for item in items)


def test_posts_new_toots():
    items = fixture_items()
    state_ids = [item["id"] for item in items[:-3]]
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(tmp, state_ids=state_ids)
        fetch_cycle(m, fake)
        buffer_handle(fake)
        m.on_tick("", 0)
        # The three newest toots, posted oldest first, action style.
        new_items = sorted(items[-3:], key=lambda item: int(item["id"]))
        assert [line for _, line in fake.commands] == [
            posted_line(m, item) for item in new_items
        ]
        logged = " ".join(fake.prnts)
        for item in new_items:
            assert f"posted {item['id']}" in logged
        assert m.load_state() == state_ids + [item["id"] for item in new_items]


def test_no_new_toots():
    items = fixture_items()
    state_ids = [item["id"] for item in items]
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(tmp, state_ids=state_ids)
        fetch_cycle(m, fake)
        buffer_handle(fake)
        m.on_tick("", 0)
        assert fake.commands == []
        assert "no new toots" in " ".join(fake.prnts)
        assert m.load_state() == state_ids


def test_holds_until_buffer_joined():
    items = fixture_items()
    state_ids = [item["id"] for item in items[:-3]]
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(tmp, state_ids=state_ids)
        fetch_cycle(m, fake)
        # The channel is not joined: nothing is posted, state unchanged.
        m.on_tick("", 0)
        assert fake.commands == []
        assert m.load_state() == state_ids
        # The channel is joined: the held toots are posted.
        buffer_handle(fake)
        m.on_tick("", 0)
        assert len(fake.commands) == 3
        new_items = sorted(items[-3:], key=lambda item: int(item["id"]))
        assert m.load_state() == state_ids + [item["id"] for item in new_items]


def test_feed_fetch_failure():
    items = fixture_items()
    state_ids = [item["id"] for item in items[:-3]]
    with tempfile.TemporaryDirectory() as tmp:
        missing = "file://" + os.path.join(tmp, "missing.rss")
        m, fake, _ = load_module(tmp, state_ids=state_ids, feed=missing)
        fetch_cycle(m, fake, feed=missing)
        # A failed fetch logs an error and changes nothing.
        assert any("failed to fetch feed" in p for p in fake.prnts)
        assert fake.commands == []
        assert m.load_state() == state_ids
        # The next healthy cycle posts the same toots.
        m, fake, _ = load_module(tmp, state_ids=state_ids)
        fetch_cycle(m, fake)
        buffer_handle(fake)
        m.on_tick("", 0)
        assert len(fake.commands) == 3


def test_cap_three_per_poll():
    items = fixture_items()
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(
            tmp, state_ids=[item["id"] for item in items[:-5]]
        )
        buffer_handle(fake)
        fetch_cycle(m, fake)
        m.on_tick("", 0)
        # A poll posts at most three toots; the rest is not lost.
        assert len(fake.commands) == 3
        assert m._pending is None
        m._next_poll = 0
        m.on_tick("", 0)
        fetch_cycle(m, fake)
        m.on_tick("", 0)
        assert len(fake.commands) == 5
        new_ids = [
            item["id"] for item in
            sorted(items[-5:], key=lambda item: int(item["id"]))
        ]
        assert m.load_state() == [item["id"] for item in items[:-5]] + new_ids


def test_long_toot_truncated():
    long_text = "word " * 100
    with tempfile.TemporaryDirectory() as tmp:
        feed = make_feed(
            tmp, "long.rss",
            [(f"<p>{long_text}</p>", "https://fosstodon.org/@farmOS/444")],
        )
        m, fake, _ = load_module(tmp, feed=feed, state_ids=[])
        fetch_cycle(m, fake, feed=feed)
        buffer_handle(fake)
        m.on_tick("", 0)
        # The line fits the cap, with the permalink kept intact.
        line = fake.commands[0][1]
        assert len(line.encode("utf-8")) <= m.MAX_LINE_BYTES
        assert line.endswith(" => https://fosstodon.org/@farmOS/444")
        assert "\u2026" in line


def test_empty_toot_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        feed = make_feed(
            tmp, "empty.rss",
            [("<p>first</p>", "https://fosstodon.org/@farmOS/111"),
             ("<p></p>", "https://fosstodon.org/@farmOS/222"),
             ("<p>third</p>", "https://fosstodon.org/@farmOS/333")],
        )
        m, fake, _ = load_module(tmp, feed=feed, state_ids=[])
        fetch_cycle(m, fake, feed=feed)
        buffer_handle(fake)
        m.on_tick("", 0)
        # The empty toot is recorded in the state, not posted.
        assert [line for _, line in fake.commands] == [
            "/me farmOS.org => first => https://fosstodon.org/@farmOS/111",
            "/me farmOS.org => third => https://fosstodon.org/@farmOS/333",
        ]
        assert "skipping toot 222: empty text" in " ".join(fake.prnts)
        assert m.load_state() == ["111", "222", "333"]


def test_state_trimmed_to_100():
    items = fixture_items()
    old_ids = [f"90000000000000000{i:02d}" for i in range(88)]
    with tempfile.TemporaryDirectory() as tmp:
        m, fake, _ = load_module(
            tmp, state_ids=old_ids + [item["id"] for item in items[3:]]
        )
        fetch_cycle(m, fake)
        buffer_handle(fake)
        m.on_tick("", 0)
        state_after = m.load_state()
        assert len(state_after) == 100
        assert state_after[0] == old_ids[8]
        new_items = sorted(items[:3], key=lambda item: int(item["id"]))
        assert state_after[-3:] == [item["id"] for item in new_items]


def main():
    """Run every test function in order; exit non-zero on any failure."""
    tests = [
        fn
        for name, fn in list(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failures = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc}", file=sys.stderr)
        else:
            print(f"ok {fn.__name__}")
    print(f"{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
