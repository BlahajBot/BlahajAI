"""OpenAI Codex OAuth upstream adapter.

The Codex backend is not a plain OpenAI-compatible API. It exposes a
Responses-like endpoint at ``chatgpt.com/backend-api/codex`` with a few
subscription-backend quirks:

* ``GET /models`` requires ``client_version=1.0.0``.
* ``POST /responses`` is streaming-only.
* ``max_output_tokens`` is rejected.
* ``input`` must be a list, not a bare string.

This adapter keeps those tweaks local to Codex while the proxy server remains a
provider-agnostic credential-attaching forwarder.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, FrozenSet, Optional
from urllib.parse import parse_qsl, urlencode

from hermes_cli.auth import (
    DEFAULT_CODEX_BASE_URL,
    _auth_store_lock,
    _load_auth_store,
    resolve_codex_runtime_credentials,
)
from hermes_cli.proxy.adapters.base import PreparedRequest, UpstreamAdapter, UpstreamCredential

logger = logging.getLogger(__name__)

_ALLOWED_PATHS: FrozenSet[str] = frozenset({"/models", "/responses"})
_DEFAULT_INSTRUCTIONS = "You are a helpful assistant."
_DEFAULT_REASONING = {"effort": "low", "summary": "auto"}


class CodexAdapter(UpstreamAdapter):
    """Proxy upstream for OpenAI Codex via Hermes-managed ChatGPT OAuth."""

    auth_hint = "hermes auth add openai-codex --type oauth"

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "OpenAI Codex"

    @property
    def allowed_paths(self) -> FrozenSet[str]:
        return _ALLOWED_PATHS

    def is_authenticated(self) -> bool:
        try:
            with _auth_store_lock():
                store = _load_auth_store()
        except Exception as exc:
            logger.debug("proxy: failed to load Codex auth store: %s", exc)
            return False

        providers = store.get("providers") if isinstance(store, dict) else None
        state = providers.get("openai-codex") if isinstance(providers, dict) else None
        if isinstance(state, dict):
            tokens = state.get("tokens")
            if isinstance(tokens, dict):
                if tokens.get("access_token") and tokens.get("refresh_token"):
                    return True

        pool = store.get("credential_pool") if isinstance(store, dict) else None
        entries = pool.get("openai-codex") if isinstance(pool, dict) else None
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("access_token"):
                    return True
        return False

    def get_credential(self) -> UpstreamCredential:
        return self._get_credential(force_refresh=False)

    def get_retry_credential(
        self,
        *,
        failed_credential: UpstreamCredential,
        status_code: int,
    ) -> Optional[UpstreamCredential]:
        _ = failed_credential
        if status_code != 401:
            return None
        logger.info("proxy: Codex upstream rejected bearer; force-refreshing OAuth token")
        return self._get_credential(force_refresh=True)

    def prepare_request(
        self,
        *,
        method: str,
        rel_path: str,
        query_string: str,
        headers: Dict[str, str],
        body: bytes,
    ) -> PreparedRequest:
        if rel_path == "/models":
            return PreparedRequest(
                method=method,
                rel_path=rel_path,
                query_string=_ensure_query_param(query_string, "client_version", "1.0.0"),
                headers=dict(headers),
                body=body,
            )

        if rel_path == "/responses":
            return self._prepare_responses_request(
                method=method,
                rel_path=rel_path,
                query_string=query_string,
                headers=headers,
                body=body,
            )

        return super().prepare_request(
            method=method,
            rel_path=rel_path,
            query_string=query_string,
            headers=headers,
            body=body,
        )

    def _get_credential(self, *, force_refresh: bool) -> UpstreamCredential:
        try:
            resolved = resolve_codex_runtime_credentials(force_refresh=force_refresh)
        except Exception as exc:
            raise RuntimeError(
                "No usable Codex OAuth credentials found. Run "
                "`hermes auth add openai-codex --type oauth` first."
            ) from exc

        bearer = str(resolved.get("api_key") or "").strip()
        if not bearer:
            raise RuntimeError(
                "Codex credential resolver did not return an access token. Run "
                "`hermes auth add openai-codex --type oauth` to re-authenticate."
            )

        base_url = str(resolved.get("base_url") or DEFAULT_CODEX_BASE_URL).strip().rstrip("/")
        return UpstreamCredential(
            bearer=bearer,
            base_url=base_url or DEFAULT_CODEX_BASE_URL,
            expires_at=resolved.get("expires_at"),
        )

    def _prepare_responses_request(
        self,
        *,
        method: str,
        rel_path: str,
        query_string: str,
        headers: Dict[str, str],
        body: bytes,
    ) -> PreparedRequest:
        try:
            payload = json.loads(body.decode("utf-8") if body else "{}")
        except Exception as exc:
            raise ValueError("Codex /responses requests must contain a JSON object body") from exc
        if not isinstance(payload, dict):
            raise ValueError("Codex /responses requests must contain a JSON object body")

        payload = dict(payload)
        payload["stream"] = True
        payload["store"] = False
        payload.pop("max_output_tokens", None)
        payload.pop("max_completion_tokens", None)

        instructions = payload.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            payload["instructions"] = _DEFAULT_INSTRUCTIONS

        payload["input"] = _normalize_responses_input(payload.get("input"))
        payload.setdefault("include", [])

        reasoning_effort = payload.pop("reasoning_effort", None)
        reasoning = payload.get("reasoning")
        if isinstance(reasoning, dict):
            payload["reasoning"] = dict(reasoning)
            if _valid_reasoning_effort(reasoning_effort) and not payload["reasoning"].get("effort"):
                payload["reasoning"]["effort"] = str(reasoning_effort).strip()
            payload["reasoning"].setdefault("summary", _DEFAULT_REASONING["summary"])
        elif _valid_reasoning_effort(reasoning_effort):
            payload["reasoning"] = {
                "effort": str(reasoning_effort).strip(),
                "summary": _DEFAULT_REASONING["summary"],
            }
        else:
            payload["reasoning"] = dict(_DEFAULT_REASONING)

        next_headers = dict(headers)
        next_headers["Accept"] = "text/event-stream"
        next_headers.setdefault("Content-Type", "application/json")
        request_id = _existing_request_id(next_headers) or f"hermes-proxy-{uuid.uuid4().hex}"
        next_headers["session_id"] = request_id
        next_headers["x-client-request-id"] = request_id

        return PreparedRequest(
            method=method,
            rel_path=rel_path,
            query_string=query_string,
            headers=next_headers,
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )


def _ensure_query_param(query_string: str, key: str, value: str) -> str:
    pairs = parse_qsl(query_string or "", keep_blank_values=True)
    if not any(k == key for k, _ in pairs):
        pairs.append((key, value))
    return urlencode(pairs)


def _existing_request_id(headers: Dict[str, str]) -> str:
    for key, value in headers.items():
        if key.lower() in {"x-client-request-id", "session_id"} and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_responses_input(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    return [{"role": "user", "content": str(value)}]


def _valid_reasoning_effort(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


__all__ = ["CodexAdapter"]
