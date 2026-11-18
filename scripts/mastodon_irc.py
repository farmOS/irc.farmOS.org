#!/usr/bin/env python3
"""Cross-post new toots from @farmOS@fosstodon.org to the #farmOS IRC room.

This is a WeeChat Python script, deployed into the WeeChat container's
scripts directory and auto-loaded on every start. WeeChat 4.x runs the
file once at load time (there is no init callback), so all setup
happens at module level. Every 10 minutes the script downloads the
account's RSS feed (via weechat.hook_process) and posts each new toot
to the irc.oftc.#farmOS buffer as an IRC action, oldest first, at most
three per poll. Already-posted toot ids are kept in a state file next
to the script (a host-mounted directory, so it survives container
restarts); on the first run the current ids are recorded without
posting. Only the Python 3 standard library (plus the weechat API) is
used.
"""

import html.parser
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import weechat

# Defaults, overridable via environment variables (used by the tests).
FEED_URL = os.environ.get(
    "MASTODON_IRC_FEED_URL", "https://fosstodon.org/@farmOS.rss"
)
BUFFER_NAME = os.environ.get("MASTODON_IRC_BUFFER", "irc.oftc.#farmOS")
STATE_FILE = os.environ.get(
    "MASTODON_IRC_STATE_FILE",
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "mastodon_irc.state.json",
    ),
)

# Limits and intervals.
TICK_MS = 1000            # timer resolution
POLL_SECONDS = 600        # poll the feed every 10 minutes
RETRY_SECONDS = 300       # retry after a failed cycle
MAX_POSTS_PER_POLL = 3    # post at most three toots per poll
MAX_STATE_ENTRIES = 100   # keep only the newest 100 posted ids
FETCH_TIMEOUT_MS = 20000  # feed download timeout
MAX_LINE_BYTES = 480      # conservative cap for the outgoing IRC line

# Module state, owned by the WeeChat main thread.
_fetching = False    # a feed download is in flight
_chunks = []         # feed body chunks from the download callback
_pending = None      # (title, toots, state) awaiting a post
_next_poll = 0       # time of the next feed poll


def log(message):
    """Write a status line to the core WeeChat buffer."""
    weechat.prnt("", f"[mastodon_irc] {message}")


# Tags whose boundaries separate toot text (they become single spaces).
BLOCK_TAGS = {
    "p", "div", "li", "blockquote", "pre", "br",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


class _TootTextParser(html.parser.HTMLParser):
    """Collect the text nodes of a toot in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS:
            self.parts.append(" ")


def html_to_text(markup):
    """Convert toot HTML to one line of plain text.

    Text nodes are concatenated in document order, so Mastodon's
    invisible/ellipsis URL spans are reconstructed in full, and block
    boundaries (paragraphs, line breaks) become single spaces.
    """
    parser = _TootTextParser()
    parser.feed(markup)
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def parse_feed(data):
    """Parse the RSS feed into (channel title, toot items), newest first.

    Each item is a dict with id (the numeric status id), url (the
    status permalink), and html (the description markup). Raises
    ValueError if the feed has no usable items.
    """
    channel = ET.fromstring(data).find("channel")
    if channel is None:
        raise ValueError("feed has no channel element")
    title = (channel.findtext("title") or "").strip() or "farmOS.org"

    items = []
    for element in channel.findall("item"):
        guid = (element.findtext("guid") or "").strip()
        status_id = guid.rsplit("/", 1)[-1]
        if not status_id.isdigit():
            raise ValueError(f"feed item has no numeric status id: {guid!r}")
        description = element.find("description")
        items.append(
            {
                "id": status_id,
                "url": (element.findtext("link") or "").strip(),
                "html": "".join(description.itertext()).strip()
                if description is not None
                else "",
            }
        )
    if not items:
        raise ValueError("feed has no items")
    return title, items


def load_state():
    """Return the list of posted toot ids, or None if it is not usable."""
    try:
        with open(STATE_FILE, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(state, list):
        return None
    return state


def save_state(state):
    """Write the posted toot ids, keeping only the newest entries."""
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state[-MAX_STATE_ENTRIES:], handle)


def start_fetch():
    """Start the RSS feed download via weechat.hook_process.

    The "url:" prefix puts hook_process in URL transfer mode, so the
    feed URL is treated as opaque data. A failed cycle is retried
    after RETRY_SECONDS; a successful cycle reschedules the next poll
    in process_feed().
    """
    global _fetching, _chunks, _next_poll
    _fetching = True
    _chunks = []
    _next_poll = time.time() + RETRY_SECONDS
    if not weechat.hook_process(
        f"url:{FEED_URL}", FETCH_TIMEOUT_MS, "on_feed_fetched", ""
    ):
        log(f"failed to start feed download: {FEED_URL}")
        _fetching = False


def on_feed_fetched(data, command, return_code, out, err):
    """Feed download callback: finish the transfer and process it."""
    global _fetching, _chunks, _next_poll
    _fetching = False
    if return_code == weechat.WEECHAT_HOOK_PROCESS_ERROR:
        detail = " ".join(err.split())
        log(f"failed to fetch feed: {detail or 'transfer failed'}")
        _next_poll = time.time() + RETRY_SECONDS
        return weechat.WEECHAT_RC_OK
    if out:
        _chunks.append(out)
    if return_code >= 0:
        process_feed("".join(_chunks))
        _chunks = []
    return weechat.WEECHAT_RC_OK


def process_feed(data):
    """Parse the feed, select new toots, and schedule the next poll."""
    global _next_poll, _pending
    try:
        title, items = parse_feed(data)
    except ValueError as exc:
        log(f"failed to parse feed: {exc}")
        _next_poll = time.time() + RETRY_SECONDS
        return
    _next_poll = time.time() + POLL_SECONDS

    state = load_state()
    if state is None:
        # First run (or lost state): record the current ids without
        # posting, so only toots published from now on are posted.
        state = [item["id"] for item in reversed(items)]
        save_state(state)
        log(f"first run: seeded state with {len(state)} toot ids")
        return

    posted = set(state)
    new = [item for item in items if item["id"] not in posted]
    new.sort(key=lambda item: int(item["id"]))
    if not new:
        log("no new toots")
        return

    new = new[:MAX_POSTS_PER_POLL]
    _pending = (title, new, state + [item["id"] for item in new])


def buffer_handle():
    """Return the channel buffer while it is joined, else None.

    The irc_buffer info returns a buffer pointer only while the
    channel is actually joined on the server, so toots are held back
    (and retried on later ticks) until then.
    """
    _, rest = BUFFER_NAME.split(".", 1)
    server, channel = rest.rsplit(".", 1)
    return weechat.info_get("irc_buffer", f"{server},{channel}") or None


def truncate_text(text, budget):
    """Truncate text to fit a byte budget, ending with an ellipsis."""
    ellipsis = "\u2026"
    limit = budget - len(ellipsis.encode("utf-8"))
    cut = text.encode("utf-8")[:limit].decode("utf-8", "ignore")
    return cut + ellipsis


def compose_line(title, text, url):
    """Compose the /me line for a toot, truncating the text if needed.

    The title and the permalink are kept intact, so the full toot
    stays reachable via the link.
    """
    prefix = f"/me {title} => "
    suffix = f" => {url}"
    budget = (
        MAX_LINE_BYTES
        - len(prefix.encode("utf-8"))
        - len(suffix.encode("utf-8"))
    )
    if len(text.encode("utf-8")) > budget:
        text = truncate_text(text, budget)
    return prefix + text + suffix


def post_pending():
    """Post the pending toots to the channel buffer."""
    global _pending
    title, toots, state = _pending
    buffer = buffer_handle()
    if buffer is None:
        return
    for toot in toots:
        text = html_to_text(toot["html"])
        if not text:
            log(f"skipping toot {toot['id']}: empty text")
            continue
        weechat.command(buffer, compose_line(title, text, toot["url"]))
        log(f"posted {toot['id']}")
    save_state(state)
    _pending = None


def on_tick(data, remaining):
    """Timer callback: start a poll when due and post pending toots."""
    try:
        if not _fetching and time.time() >= _next_poll:
            start_fetch()
        if _pending is not None:
            post_pending()
    except Exception as exc:
        # Never raise out of the hook callback.
        log(f"error: {exc!r}")
    return weechat.WEECHAT_RC_OK


# WeeChat 4.x runs the file once at load time, so all setup happens
# here, right after registration: the timer hook and the first feed
# download.
weechat.register(
    "mastodon_irc",
    "farmOS project",
    "1.0",
    "GPL-3.0",
    "Cross-post farmOS toots from fosstodon.org to #farmOS",
    "",
    "utf-8",
)
weechat.hook_timer(TICK_MS, 0, 0, "on_tick", "")
log(f"loaded (feed {FEED_URL}, buffer {BUFFER_NAME}, state {STATE_FILE})")
start_fetch()
