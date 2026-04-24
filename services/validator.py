from __future__ import annotations

import json
import logging
import re
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
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
        probe_server_ip: str,
        redis_client: Any | None = None,
        probe_server_port: int = 8080,
        http_timeout: float = 45.0,
        disposable_list_timeout: float = 15.0,
        dns_timeout: float = 5.0,
    ) -> None:
        self.probe_server_ip = probe_server_ip
        self.probe_server_port = probe_server_port
        self.redis_client = redis_client
        self.http_timeout = http_timeout
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

        smtp_result = self._probe_email(normalized_email)
        if smtp_result is not None:
            if smtp_result.status == "valid" and role_flag is not None:
                return role_flag
            return smtp_result

        if role_flag is not None:
            return role_flag

        return ValidationResult(
            email=normalized_email,
            status="risky",
            reason="smtp_timeout",
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

    def _probe_email(self, email: str) -> ValidationResult | None:
        url = self._build_probe_url(email)
        payload = ""
        http_status: int | None = None

        try:
            with urllib_request.urlopen(url, timeout=self.http_timeout) as response:
                http_status = getattr(response, "status", None)
                payload = response.read().decode("utf-8", errors="ignore").strip()
        except urllib_error.HTTPError as exc:
            http_status = exc.code
            payload = exc.read().decode("utf-8", errors="ignore").strip()
        except (urllib_error.URLError, socket.timeout, TimeoutError):
            return ValidationResult(email=email, status="risky", reason="probe_unreachable")

        parsed_payload = self._parse_probe_payload(payload)
        parsed_result = self._extract_probe_result(email=email, parsed_payload=parsed_payload)
        if parsed_result is not None:
            return parsed_result

        if self._is_catch_all(http_status=http_status, parsed_payload=parsed_payload):
            return ValidationResult(email=email, status="risky", reason="catch_all")

        probe_code = self._extract_probe_code(http_status=http_status, parsed_payload=parsed_payload)

        if probe_code == 250:
            return ValidationResult(email=email, status="valid", reason="smtp_ok")
        if probe_code == 550:
            return ValidationResult(email=email, status="invalid", reason="smtp_reject")
        if probe_code is None:
            return ValidationResult(email=email, status="risky", reason="probe_timeout")

        return ValidationResult(email=email, status="risky", reason="probe_timeout")

    def _build_probe_url(self, email: str) -> str:
        query = urllib_parse.urlencode({"email": email})
        return f"http://{self.probe_server_ip}:{self.probe_server_port}/probe?{query}"

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

    def _parse_probe_payload(self, payload: str) -> Any:
        if not payload:
            return None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload.strip().lower()

    def _is_catch_all(self, http_status: int | None, parsed_payload: Any) -> bool:
        if isinstance(parsed_payload, dict):
            if self._is_truthy(parsed_payload.get("catch_all")):
                return True
            for key in ("result", "reason", "status"):
                value = parsed_payload.get(key)
                if isinstance(value, str) and "catch_all" in value.lower().replace("-", "_"):
                    return True

        if isinstance(parsed_payload, str) and "catch_all" in parsed_payload.replace("-", "_"):
            return True

        return False

    def _extract_probe_result(
        self,
        email: str,
        parsed_payload: Any,
    ) -> ValidationResult | None:
        if not isinstance(parsed_payload, dict):
            return None

        raw_status = str(parsed_payload.get("status") or "").strip().lower()
        raw_reason = str(parsed_payload.get("reason") or "").strip().lower()

        if raw_status in {"valid", "risky", "invalid"}:
            return ValidationResult(
                email=email,
                status=raw_status,
                reason=raw_reason or "probe_response",
            )

        if raw_status == "error":
            return ValidationResult(
                email=email,
                status="risky",
                reason=raw_reason or "probe_error",
            )

        return None

    def _extract_probe_code(self, http_status: int | None, parsed_payload: Any) -> int | None:
        if isinstance(parsed_payload, dict):
            for key in ("smtp_code", "code", "status_code"):
                value = parsed_payload.get(key)
                parsed_value = self._coerce_int(value)
                if parsed_value is not None:
                    return parsed_value

        if isinstance(parsed_payload, str):
            parsed_value = self._coerce_int(parsed_payload)
            if parsed_value is not None:
                return parsed_value

        return http_status

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        return bool(value)

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
