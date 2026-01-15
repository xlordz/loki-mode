"""
Built-in guardrails for the Autonomi SDK.
"""

import re
from typing import List, Optional, Pattern

from autonomi.guardrails.base import (
    InputGuardrail,
    OutputGuardrail,
    GuardrailResult,
)


class InjectionDetector(InputGuardrail):
    """
    Detects potential prompt injection attempts.

    Looks for patterns commonly used in injection attacks.
    """

    name = "injection_detector"
    description = "Detects prompt injection attempts"

    DEFAULT_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?prior\s+instructions",
        r"disregard\s+(all\s+)?previous",
        r"forget\s+(all\s+)?previous",
        r"system\s*prompt\s*:",
        r"<\|.*?\|>",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"you\s+are\s+now\s+",
        r"act\s+as\s+if\s+",
        r"pretend\s+(to\s+be|you're|you\s+are)",
        r"new\s+instructions\s*:",
        r"override\s+(instructions|prompt)",
    ]

    def __init__(self, patterns: Optional[List[str]] = None, strict: bool = False):
        """
        Initialize the injection detector.

        Args:
            patterns: Custom patterns to detect (in addition to defaults)
            strict: If True, any match blocks. If False, escalates.
        """
        self.patterns: List[Pattern[str]] = []
        for p in self.DEFAULT_PATTERNS:
            self.patterns.append(re.compile(p, re.IGNORECASE))

        if patterns:
            for p in patterns:
                self.patterns.append(re.compile(p, re.IGNORECASE))

        self.strict = strict

    async def check(self, value: str) -> GuardrailResult:
        """Check for injection patterns."""
        for pattern in self.patterns:
            match = pattern.search(value)
            if match:
                reason = f"Potential injection detected: '{match.group()}'"
                if self.strict:
                    return GuardrailResult.block(reason)
                else:
                    return GuardrailResult.escalate(reason)

        return GuardrailResult.allow()


class SecretScanner(OutputGuardrail):
    """
    Scans for secrets in output and redacts them.

    Detects API keys, tokens, passwords, and other sensitive data.
    """

    name = "secret_scanner"
    description = "Scans for and redacts secrets"

    SECRET_PATTERNS = [
        # API Keys
        (r"sk-[a-zA-Z0-9]{20,}", "API key"),
        (r"sk-ant-[a-zA-Z0-9-]{20,}", "Anthropic API key"),
        (r"sk-proj-[a-zA-Z0-9-]{20,}", "OpenAI project key"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token"),
        (r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}", "GitHub fine-grained token"),
        (r"xoxb-[0-9]{11}-[0-9]{11}-[a-zA-Z0-9]{24}", "Slack bot token"),
        (r"xoxp-[0-9]{11}-[0-9]{11}-[0-9]{11}-[a-f0-9]{32}", "Slack user token"),

        # Passwords
        (r"(?i)password\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", "password"),
        (r"(?i)passwd\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", "password"),
        (r"(?i)secret\s*[=:]\s*['\"]?[^\s'\"]{8,}['\"]?", "secret"),

        # Private keys
        (r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", "private key"),
        (r"-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----", "SSH private key"),

        # Connection strings
        (r"(?i)mongodb(?:\+srv)?://[^\s]+", "MongoDB connection string"),
        (r"(?i)postgres(?:ql)?://[^\s]+", "PostgreSQL connection string"),
        (r"(?i)mysql://[^\s]+", "MySQL connection string"),
        (r"(?i)redis://[^\s]+", "Redis connection string"),
    ]

    def __init__(self, redact: bool = True, block_on_secret: bool = False):
        """
        Initialize the secret scanner.

        Args:
            redact: If True, redact secrets. If False, just report.
            block_on_secret: If True, block output with secrets.
        """
        self.patterns = [(re.compile(p), desc) for p, desc in self.SECRET_PATTERNS]
        self.redact = redact
        self.block_on_secret = block_on_secret

    async def check(self, value: str) -> GuardrailResult:
        """Scan for secrets."""
        found_secrets: List[str] = []
        redacted_value = value

        for pattern, description in self.patterns:
            matches = pattern.findall(redacted_value)
            if matches:
                found_secrets.append(description)
                if self.redact:
                    redacted_value = pattern.sub(f"[REDACTED {description}]", redacted_value)

        if found_secrets:
            reason = f"Secrets detected: {', '.join(set(found_secrets))}"

            if self.block_on_secret:
                return GuardrailResult.block(reason)

            if self.redact:
                return GuardrailResult.transform(redacted_value, reason)

            return GuardrailResult.escalate(reason)

        return GuardrailResult.allow()


class PIIRedactor(OutputGuardrail):
    """
    Redacts personally identifiable information (PII).
    """

    name = "pii_redactor"
    description = "Redacts PII from output"

    PII_PATTERNS = [
        # Email
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),

        # Phone (US formats)
        (r"\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b", "[PHONE]"),

        # SSN
        (r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b", "[SSN]"),

        # Credit card
        (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b", "[CARD]"),

        # IP addresses
        (r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "[IP]"),
    ]

    def __init__(self, patterns: Optional[List[tuple[str, str]]] = None):
        """
        Initialize the PII redactor.

        Args:
            patterns: Additional (pattern, replacement) pairs
        """
        self.patterns = [(re.compile(p), r) for p, r in self.PII_PATTERNS]
        if patterns:
            for p, r in patterns:
                self.patterns.append((re.compile(p), r))

    async def check(self, value: str) -> GuardrailResult:
        """Redact PII."""
        redacted = value
        found_pii = False

        for pattern, replacement in self.patterns:
            if pattern.search(redacted):
                found_pii = True
                redacted = pattern.sub(replacement, redacted)

        if found_pii:
            return GuardrailResult.transform(redacted, "PII redacted")

        return GuardrailResult.allow()


class ContentPolicyChecker(InputGuardrail):
    """
    Checks content against a simple policy.

    For production use, consider integrating with a dedicated
    content moderation API.
    """

    name = "content_policy"
    description = "Checks content against policy"

    DEFAULT_BLOCKED_TERMS = [
        # Violence
        "kill", "murder", "attack", "bomb", "weapon",
        # Illegal
        "illegal", "hack", "crack", "exploit", "steal",
    ]

    def __init__(
        self,
        blocked_terms: Optional[List[str]] = None,
        use_defaults: bool = False,
    ):
        """
        Initialize the policy checker.

        Args:
            blocked_terms: Terms to block
            use_defaults: Whether to include default blocked terms
        """
        terms = []
        if use_defaults:
            terms.extend(self.DEFAULT_BLOCKED_TERMS)
        if blocked_terms:
            terms.extend(blocked_terms)

        self.blocked_pattern = None
        if terms:
            pattern = r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b"
            self.blocked_pattern = re.compile(pattern, re.IGNORECASE)

    async def check(self, value: str) -> GuardrailResult:
        """Check against policy."""
        if self.blocked_pattern:
            match = self.blocked_pattern.search(value)
            if match:
                return GuardrailResult.block(
                    f"Content policy violation: '{match.group()}'"
                )

        return GuardrailResult.allow()


class LengthValidator(InputGuardrail):
    """
    Validates input length.
    """

    name = "length_validator"
    description = "Validates input length"

    def __init__(self, min_length: int = 0, max_length: int = 100000):
        """
        Initialize the length validator.

        Args:
            min_length: Minimum allowed length
            max_length: Maximum allowed length
        """
        self.min_length = min_length
        self.max_length = max_length

    async def check(self, value: str) -> GuardrailResult:
        """Validate length."""
        length = len(value)

        if length < self.min_length:
            return GuardrailResult.block(
                f"Input too short: {length} < {self.min_length}"
            )

        if length > self.max_length:
            return GuardrailResult.block(
                f"Input too long: {length} > {self.max_length}"
            )

        return GuardrailResult.allow()
