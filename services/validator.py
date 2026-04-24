from __future__ import annotations

import logging
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import dns.exception
import dns.resolver


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ValidationResult:
    email: str
    status: str
    reason: str


class EmailValidator:
    SYNTAX_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
    DISPOSABLE_LIST_URL = (
        "https://raw.githubusercontent.com/disposable-email-domains/"
        "disposable-email-domains/master/disposable_email_blocklist.conf"
    )
    ROLE_PREFIXES = {
        "info",
        "support",
        "admin",
        "sales",
        "contact",
        "noreply",
        "no-reply",
        "hello",
        "team",
        "billing",
        "help",
    }
    MX_CACHE_TTL_SECONDS = 60 * 60 * 24

    def __init__(
        self,
        redis_client: Any | None = None,
        disposable_list_timeout: float = 15.0,
        dns_timeout: float = 5.0,
    ) -> None:
        self.redis_client = redis_client
        self.disposable_list_timeout = disposable_list_timeout
        self.disposable_domains = self._load_disposable_domains()
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = dns_timeout
        self.resolver.lifetime = dns_timeout

    def deduplicate_emails(self, emails: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        deduplicated: list[str] = []

        for email in emails:
            normalized = self.normalize_email(email)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(normalized)

        return deduplicated

    def validate_emails(self, emails: Iterable[str]) -> list[ValidationResult]:
        return [self.validate_email(email) for email in self.deduplicate_emails(emails)]

    def validate_email(self, email: str) -> ValidationResult:
        normalized_email = self.normalize_email(email)

        syntax_result = self._check_syntax(normalized_email)
        if syntax_result is not None:
            return syntax_result

        role_flag = self._check_role_address(normalized_email)

        disposable_result = self._check_disposable_domain(normalized_email)
        if disposable_result is not None:
            return disposable_result

        mx_result = self._check_mx(normalized_email)
        if mx_result is not None:
            return mx_result

        if role_flag is not None:
            return role_flag

        return ValidationResult(
            email=normalized_email,
            status="valid",
            reason="mx_passed",
        )

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def _check_syntax(self, email: str) -> ValidationResult | None:
        if self.SYNTAX_REGEX.fullmatch(email):
            return None
        return ValidationResult(email=email, status="invalid", reason="bad_syntax")

    def _check_role_address(self, email: str) -> ValidationResult | None:
        local_part = email.split("@", 1)[0]
        if any(local_part.startswith(prefix) for prefix in self.ROLE_PREFIXES):
            return ValidationResult(email=email, status="risky", reason="role_address")
        return None

    def _check_disposable_domain(self, email: str) -> ValidationResult | None:
        domain = email.rsplit("@", 1)[1]
        if domain in self.disposable_domains:
            return ValidationResult(
                email=email,
                status="invalid",
                reason="disposable_domain",
            )
        return None

    def _check_mx(self, email: str) -> ValidationResult | None:
        domain = email.rsplit("@", 1)[1]
        cache_key = f"mx:{domain}"
        cached_value = self._redis_get(cache_key)

        if cached_value is not None:
            if cached_value == "1":
                return None
            return ValidationResult(email=email, status="invalid", reason="no_mx")

        try:
            answers = self.resolver.resolve(domain, "MX")
            has_mx = any(True for _ in answers)
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.resolver.LifetimeTimeout,
            dns.exception.DNSException,
        ):
            has_mx = False

        self._redis_setex(
            cache_key,
            self.MX_CACHE_TTL_SECONDS,
            "1" if has_mx else "0",
        )

        if has_mx:
            return None

        return ValidationResult(email=email, status="invalid", reason="no_mx")

    def _load_disposable_domains(self) -> set[str]:
        request = urllib_request.Request(
            self.DISPOSABLE_LIST_URL,
            headers={"User-Agent": "EmailVerifier/1.0"},
        )

        try:
            with urllib_request.urlopen(
                request,
                timeout=self.disposable_list_timeout,
            ) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except (urllib_error.URLError, socket.timeout, TimeoutError) as exc:
            LOGGER.warning("Failed to download disposable domain list: %s", exc)
            return set()

        domains = {
            line.strip().lower()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        return domains

    def _redis_get(self, key: str) -> str | None:
        if self.redis_client is None:
            return None

        try:
            value = self.redis_client.get(key)
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.warning("Redis GET failed for %s: %s", key, exc)
            return None

        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def _redis_setex(self, key: str, ttl_seconds: int, value: str) -> None:
        if self.redis_client is None:
            return

        try:
            self.redis_client.setex(key, ttl_seconds, value)
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.warning("Redis SETEX failed for %s: %s", key, exc)
