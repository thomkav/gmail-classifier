#!/usr/bin/env python3
"""
Extract Unsubscribe Links by Domain

Connects via IMAP to Gmail, fetches one email per domain from All Mail,
extracts unsubscribe links from List-Unsubscribe headers or HTML body.

Modes:
  (default)  Print links only — no side effects
  --auto     POST one-click unsubscribe (RFC 8058) where supported
  --open     Open unsubscribe URLs in default browser
"""

import imaplib
import email
import email.utils
import html.parser
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import webbrowser


class UnsubscribeLinkExtractor(html.parser.HTMLParser):
    """Extract unsubscribe links from HTML email bodies."""

    def __init__(self):
        super().__init__()
        self.links = []
        self._in_a = False
        self._current_href = None
        self._current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            self._current_text = ""
            for name, value in attrs:
                if name == "href" and value:
                    self._current_href = value

    def handle_data(self, data):
        if self._in_a:
            self._current_text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            self._in_a = False
            if self._current_href:
                href_lower = self._current_href.lower()
                text_lower = self._current_text.lower()
                if "unsubscribe" in href_lower or "unsubscribe" in text_lower:
                    if href_lower.startswith("http://") or href_lower.startswith("https://"):
                        self.links.append(self._current_href)
            self._current_href = None
            self._current_text = ""


def connect_imap(readonly=True):
    """Connect to Gmail IMAP and select All Mail."""
    user = os.environ.get("GMAIL_EMAIL", "thomkav@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("ERROR: GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    print("Connecting to imap.gmail.com...", file=sys.stderr)
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    mail.login(user, password)
    mail.select('"[Gmail]/All Mail"', readonly=readonly)
    return mail


def parse_list_unsubscribe_header(header_value):
    """Parse List-Unsubscribe header into http and mailto links.

    Format: <https://example.com/unsub>, <mailto:unsub@example.com>
    """
    http_links = []
    mailto_links = []

    # Extract angle-bracketed URLs
    urls = re.findall(r"<([^>]+)>", header_value)
    for url in urls:
        url = url.strip()
        if url.lower().startswith("https://") or url.lower().startswith("http://"):
            http_links.append(url)
        elif url.lower().startswith("mailto:"):
            mailto_links.append(url)

    return http_links, mailto_links


def extract_links_from_html(html_body):
    """Extract unsubscribe links from HTML email body."""
    parser = UnsubscribeLinkExtractor()
    try:
        parser.feed(html_body)
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for link in parser.links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def get_email_html_body(mail, msg_id):
    """Fetch and decode the HTML body of an email."""
    status, data = mail.fetch(msg_id, "(BODY.PEEK[])")
    if status != "OK" or not data or not data[0]:
        return ""

    raw = data[0][1] if isinstance(data[0], tuple) else b""
    msg = email.message_from_bytes(raw)

    # Walk MIME parts looking for text/html
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")

    # Fallback: if not multipart, try the whole body
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")

    return ""


def extract_unsubscribe_for_domain(mail, domain):
    """Extract unsubscribe info for a single domain.

    Returns a dict with domain, email_found, source, http_links, one_click, mailto_links.
    """
    result = {
        "domain": domain,
        "email_found": False,
        "source": None,
        "http_links": [],
        "one_click": False,
        "mailto_links": [],
    }

    # Search for emails from this domain
    status, data = mail.search(None, 'FROM', f'"@{domain}"')
    if status != "OK" or not data[0]:
        return result

    msg_ids = data[0].split()
    if not msg_ids:
        return result

    result["email_found"] = True
    # Take the most recent email (last ID)
    msg_id = msg_ids[-1]

    # Try List-Unsubscribe header first
    status, data = mail.fetch(
        msg_id, "(BODY.PEEK[HEADER.FIELDS (List-Unsubscribe List-Unsubscribe-Post)])"
    )
    if status == "OK" and data and data[0]:
        header_raw = data[0][1] if isinstance(data[0], tuple) else b""
        if isinstance(header_raw, bytes):
            header_raw = header_raw.decode("utf-8", errors="replace")

        # Parse List-Unsubscribe
        unsub_match = re.search(
            r"List-Unsubscribe:\s*(.+?)(?:\r?\n(?!\s)|\Z)",
            header_raw,
            re.IGNORECASE | re.DOTALL,
        )
        if unsub_match:
            header_value = unsub_match.group(1).strip()
            http_links, mailto_links = parse_list_unsubscribe_header(header_value)

            if http_links or mailto_links:
                result["source"] = "header"
                result["http_links"] = http_links
                result["mailto_links"] = mailto_links

                # Check for RFC 8058 one-click support
                if re.search(r"List-Unsubscribe-Post:", header_raw, re.IGNORECASE):
                    result["one_click"] = True

    # Fallback to HTML body if no header links found
    if not result["http_links"]:
        html_body = get_email_html_body(mail, msg_id)
        if html_body:
            html_links = extract_links_from_html(html_body)
            if html_links:
                result["source"] = "html"
                result["http_links"] = html_links

    return result


def post_one_click_unsubscribe(url):
    """POST a one-click unsubscribe request per RFC 8058."""
    body = b"List-Unsubscribe=One-Click"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "gmail-classifier/1.0 (unsubscribe)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status < 400
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  POST failed: {e}", file=sys.stderr)
        return False


def main():
    auto_mode = "--auto" in sys.argv
    open_mode = "--open" in sys.argv
    domains = [arg for arg in sys.argv[1:] if arg not in ("--auto", "--open")]

    if not domains:
        print("Usage: python3 extract_unsubscribe.py [--auto|--open] domain1 domain2 ...")
        print("  --auto   One-click unsubscribe via HTTP POST (RFC 8058) where supported")
        print("  --open   Open unsubscribe URLs in default browser")
        print("  (default) Print URLs only — no action taken")
        sys.exit(1)

    mail = connect_imap(readonly=True)

    results = []
    for domain in domains:
        print(f"  Checking {domain}...", file=sys.stderr)
        result = extract_unsubscribe_for_domain(mail, domain)
        results.append(result)

        if not result["email_found"]:
            print(f"    No emails found", file=sys.stderr)
        elif not result["http_links"]:
            print(f"    No unsubscribe links found", file=sys.stderr)
        else:
            source = result["source"]
            n = len(result["http_links"])
            one_click = " (one-click)" if result["one_click"] else ""
            print(f"    Found {n} link(s) via {source}{one_click}", file=sys.stderr)

        time.sleep(0.3)

    mail.close()
    mail.logout()

    # Action modes
    if auto_mode:
        print("\n=== Auto-unsubscribe (RFC 8058 one-click) ===", file=sys.stderr)
        for r in results:
            if r["one_click"] and r["http_links"]:
                url = r["http_links"][0]
                print(f"  POSTing to {r['domain']}...", file=sys.stderr)
                success = post_one_click_unsubscribe(url)
                r["auto_result"] = "success" if success else "failed"
                print(f"    {'Success' if success else 'Failed'}", file=sys.stderr)
            elif r["http_links"]:
                r["auto_result"] = "skipped (no one-click support)"
            else:
                r["auto_result"] = "skipped (no links)"

    if open_mode:
        print("\n=== Opening unsubscribe links in browser ===", file=sys.stderr)
        for r in results:
            for url in r["http_links"]:
                print(f"  Opening {url[:80]}...", file=sys.stderr)
                webbrowser.open(url)
                time.sleep(0.5)

    # Output JSON
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
