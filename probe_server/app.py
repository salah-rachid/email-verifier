from __future__ import annotations

import logging
import re
import smtplib
import socket
import threading
import time
from collections import defaultdict
from collections import deque
from datetime import datetime
from typing import Deque

import dns.exception
import dns.resolver
from flask import Flask
from flask import jsonify
from flask import request


LOGGER = logging.getLogger(__name__)

app = Flask(__name__)

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
FAKE_LOCAL_PART = "xzqq_fake_99"
MAIL_FROM_ADDRESS = "probe@emailverifier.local"
SMTP_PORT = 25
SMTP_TIMEOUT_SECONDS = 15
SMTP_RETRY_DELAY_SECONDS = 5
SMTP_RETRY_CODES = {421, 450, 451, 452}
MAX_PROBES_PER_DAY = 200
MAX_PROBES_PER_DOMAIN_PER_HOUR = 10
DOMAIN_PROBE_DELAY_SECONDS = 3
DOMAIN_WINDOW_SECONDS = 60 * 60
DNS_TIMEOUT_SECONDS = 5


class ProbeLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_day = datetime.now().date()
        self._probes_today = 0
        self._domain_timestamps: dict[str, Deque[float]] = defaultdict(deque)
        self._domain_next_probe_at: dict[str, float] = defaultdict(float)

    def reserve(self, domain: str) -> tuple[bool, float, str | None]:
        now_epoch = time.time()
        now_monotonic = time.monotonic()

        with self._lock:
            self._reset_day_if_needed()

            if self._probes_today >= MAX_PROBES_PER_DAY:
                return False, 0.0, "daily_limit_reached"

            timestamps = self._domain_timestamps[domain]
            cutoff = now_epoch - DOMAIN_WINDOW_SECONDS
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= MAX_PROBES_PER_DOMAIN_PER_HOUR:
                return False, 0.0, "domain_rate_limited"

            scheduled_at = max(now_monotonic, self._domain_next_probe_at[domain])
            wait_seconds = max(0.0, scheduled_at - now_monotonic)
            self._domain_next_probe_at[domain] = scheduled_at + DOMAIN_PROBE_DELAY_SECONDS

            timestamps.append(now_epoch)
            self._probes_today += 1

        return True, wait_seconds, None

    def probes_today(self) -> int:
        with self._lock:
            self._reset_day_if_needed()
            return self._probes_today

    def _reset_day_if_needed(self) -> None:
        today = datetime.now().date()
        if today != self._current_day:
            self._current_day = today
            self._probes_today = 0


limiter = ProbeLimiter()
resolver = dns.resolver.Resolver()
resolver.timeout = DNS_TIMEOUT_SECONDS
resolver.lifetime = DNS_TIMEOUT_SECONDS


@app.get("/probe")
def probe() -> tuple[object, int] | object:
    email = (request.args.get("email") or "").strip().lower()
    if not EMAIL_REGEX.fullmatch(email):
        return jsonify({"status": "invalid", "reason": "bad_syntax"}), 400

    domain = email.rsplit("@", 1)[1]
    allowed, wait_seconds, rejection_reason = limiter.reserve(domain)
    if not allowed:
        return jsonify({"status": "error", "reason": rejection_reason}), 429

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    fake_email = f"{FAKE_LOCAL_PART}@{domain}"
    catch_all_code = probe_recipient(fake_email)
    if catch_all_code == 250:
        return jsonify({"status": "risky", "reason": "catch_all"})

    mailbox_code = probe_mailbox(email)
    if mailbox_code == 250:
        return jsonify({"status": "valid", "reason": "smtp_ok", "code": 250})
    if mailbox_code == 550:
        return jsonify({"status": "invalid", "reason": "smtp_reject", "code": 550})

    return jsonify({"status": "risky", "reason": "smtp_timeout", "code": None})


@app.get("/health")
def health() -> object:
    return jsonify({"status": "ok", "probes_today": limiter.probes_today()})


def probe_mailbox(email: str) -> int | None:
    first_code = probe_recipient(email)
    if first_code in SMTP_RETRY_CODES:
        time.sleep(SMTP_RETRY_DELAY_SECONDS)
        return probe_recipient(email)
    return first_code


def probe_recipient(email: str) -> int | None:
    domain = email.rsplit("@", 1)[1]
    mx_hosts = resolve_mx_hosts(domain)
    if not mx_hosts:
        return None

    for mx_host in mx_hosts:
        code = rcpt_to(mx_host, email)
        if code is not None:
            return code

    return None


def resolve_mx_hosts(domain: str) -> list[str]:
    try:
        answers = resolver.resolve(domain, "MX")
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.resolver.LifetimeTimeout,
        dns.exception.DNSException,
    ) as exc:
        LOGGER.warning("MX lookup failed for %s: %s", domain, exc)
        return []

    records = sorted(
        (
            (record.preference, str(record.exchange).rstrip("."))
            for record in answers
        ),
        key=lambda item: item[0],
    )
    return [host for _, host in records]


def rcpt_to(mx_host: str, recipient_email: str) -> int | None:
    smtp: smtplib.SMTP | None = None

    try:
        smtp = smtplib.SMTP(timeout=SMTP_TIMEOUT_SECONDS)
        smtp.connect(mx_host, SMTP_PORT)
        smtp.ehlo_or_helo_if_needed()

        mail_code, _ = smtp.mail(MAIL_FROM_ADDRESS)
        if mail_code not in (250, 251):
            return None

        rcpt_code, _ = smtp.rcpt(recipient_email)
        return int(rcpt_code)
    except (
        OSError,
        socket.timeout,
        TimeoutError,
        smtplib.SMTPConnectError,
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPResponseException,
    ) as exc:
        LOGGER.warning("SMTP probe failed for %s via %s: %s", recipient_email, mx_host, exc)
        return None
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=8080)
