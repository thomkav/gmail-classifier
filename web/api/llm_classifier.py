"""LLM-based domain classification via local LiteLLM MLX stack.

Endpoint: http://127.0.0.1:49100/v1 (OpenAI-compatible, no auth)
Model: local/coder (Qwen2.5-Coder-7B)

Hardening:
- Single-flight semaphore so two `/jobs classify` requests don't double-load MLX
- /api/llm/status probe with cached health
- Exponential backoff on 5xx/timeout (3 retries, jitter)
- Warming-up detection: first request after cold start emits `llm.warming` SSE
- Configurable timeout via LLM_TIMEOUT env (default 60s)
"""
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from constants import CONFIG_JSON

_config_lock = threading.Lock()
_llm_semaphore = threading.Semaphore(1)
_status_cache: dict = {"up": None, "model": None, "warming_up": False, "last_latency_ms": None, "last_checked": 0.0, "error": None}
_status_lock = threading.Lock()

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:49100/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "local/coder")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))
LLM_WARM_TIMEOUT = int(os.environ.get("LLM_WARM_TIMEOUT", "180"))  # cold-start MLX swap can take ~2min
BATCH_SIZE = 20
VALID_CATEGORIES = {"newsletter", "promotion", "receipt", "notification", "personal", "unknown"}


def _load_cache_key(key: str) -> dict:
    with _config_lock:
        if not CONFIG_JSON.exists():
            return {}
        try:
            return json.loads(CONFIG_JSON.read_text()).get(key, {})
        except (json.JSONDecodeError, OSError):
            return {}


def _is_error_result(r: dict) -> bool:
    reasoning = (r.get("reasoning") or "").lower()
    if r.get("confidence", 0) == 0 or "llm error" in reasoning or "no result" in reasoning:
        return True
    # "personal" and low-confidence results are not applied by classify_domains (it excludes them
    # from overriding rule-based unknowns), so caching them would permanently block re-classification.
    if r.get("category") in ("personal", "unknown"):
        return True
    return False


def _save_cache_key(key: str, data: dict) -> None:
    with _config_lock:
        try:
            cfg = json.loads(CONFIG_JSON.read_text()) if CONFIG_JSON.exists() else {}
        except (json.JSONDecodeError, OSError):
            cfg = {}
        cfg[key] = data
        CONFIG_JSON.write_text(json.dumps(cfg, indent=2) + "\n")


def classify_domains_llm(domain_subjects: dict, on_batch_done=None) -> dict:
    """Classify domains using the local LLM, single-flight, with cache + backoff.

    Args:
        domain_subjects: {domain: [subject1, ...]}
        on_batch_done: optional callback(batch_results: dict)

    Returns:
        {domain: {"category": ..., "confidence": ..., "reasoning": ...}}
    """
    cache = _load_cache_key("llm_classifications")
    results = {d: cache[d] for d in domain_subjects if d in cache}
    to_classify = [(d, s) for d, s in domain_subjects.items() if d not in cache]

    if on_batch_done and results:
        on_batch_done(results)

    if not to_classify:
        return results

    acquired = _llm_semaphore.acquire(blocking=True, timeout=LLM_WARM_TIMEOUT)
    if not acquired:
        # Another classify is in-flight beyond our patience window — fail fast
        # rather than queueing forever.
        for domain, _ in to_classify:
            results[domain] = {"category": "unknown", "confidence": 0, "reasoning": "LLM busy (timeout)"}
        return results

    try:
        for i in range(0, len(to_classify), BATCH_SIZE):
            batch = to_classify[i:i + BATCH_SIZE]
            batch_results = _classify_batch_with_retry(batch)
            for domain, result in batch_results.items():
                results[domain] = result
                # Don't poison the cache with error rows — re-try those next time.
                if not _is_error_result(result):
                    cache[domain] = result
            _save_cache_key("llm_classifications", cache)
            if on_batch_done:
                on_batch_done(batch_results)
            if i + BATCH_SIZE < len(to_classify):
                time.sleep(0.1)
    finally:
        _llm_semaphore.release()

    return results


def _classify_batch_with_retry(batch: list, max_retries: int = 3) -> dict:
    """Wrap _classify_batch with exponential backoff + jitter on transient errors."""
    last_err: str | None = None
    for attempt in range(max_retries + 1):
        # First attempt: warm timeout (covers MLX cold start). Subsequent: regular.
        timeout = LLM_WARM_TIMEOUT if attempt == 0 else LLM_TIMEOUT
        try:
            t0 = time.time()
            out = _classify_batch(batch, timeout=timeout)
            _record_status(up=True, latency_ms=int((time.time() - t0) * 1000), error=None)
            return out
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code < 500 or attempt == max_retries:
                _record_status(up=False, error=last_err)
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = str(e)
            if attempt == max_retries:
                _record_status(up=False, error=last_err)
                break
        delay = (0.5 * (2 ** attempt)) + random.uniform(0, 0.3)
        time.sleep(delay)

    return {domain: {"category": "unknown", "confidence": 0, "reasoning": f"LLM error: {last_err}"} for domain, _ in batch}


def _classify_batch(batch: list, timeout: int = LLM_TIMEOUT) -> dict:
    domain_lines = []
    for idx, (domain, subjects) in enumerate(batch, 1):
        sample = subjects[:3]
        subjects_str = " | ".join(f'"{s}"' for s in sample) if sample else "(no subjects)"
        domain_lines.append(f"{idx}. {domain} — {subjects_str}")

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are an email sender domain classifier. Return ONLY a valid JSON array, no explanation, no markdown.",
            },
            {
                "role": "user",
                "content": (
                    "Classify these email sender domains.\n\n"
                    "Categories: newsletter | promotion | receipt | notification | personal | unknown\n"
                    "- newsletter: editorial content, digests, blog posts, community updates, advocacy org updates, educational content, research summaries — even if they have a call-to-action\n"
                    "- promotion: purely commercial marketing — sales, discounts, product launches, commercial event ticket sales. NOT appointment reminders, NOT nonprofit/advocacy content, NOT community events\n"
                    "- receipt: order confirmations, invoices, shipping notices, booking confirmations, appointment reminders, donation receipts\n"
                    "- notification: account alerts, security notices, service updates, password resets, file shares, social platform notifications\n"
                    "- personal: clearly from a real individual to the recipient personally (reply threads, direct human correspondence)\n"
                    "- unknown: cannot determine with reasonable confidence\n\n"
                    "Key distinctions:\n"
                    "- Appointment/booking reminders → receipt (transactional, time-specific)\n"
                    "- Nonprofit/advocacy/community orgs → newsletter (not promotion, even with fundraising asks)\n"
                    "- File transfer services (WeTransfer etc.) → notification\n"
                    "- Financial account updates → notification\n"
                    "- Small org or individual-sounding sender that sends bulk content → newsletter (not personal)\n\n"
                    'Return JSON array: [{"domain": "...", "category": "...", "confidence": 0-100, "reasoning": "brief"}]\n\n'
                    "Domains:\n" + "\n".join(domain_lines)
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 2400,
    }).encode()

    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Errors propagate so the caller (_classify_batch_with_retry) can decide.
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    content = data["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content_lines = content.split("\n")
        end = -1 if content_lines[-1].strip() == "```" else len(content_lines)
        content = "\n".join(content_lines[1:end])

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', content, re.DOTALL)
        parsed = []
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    results = {}
    for item in parsed:
        domain = item.get("domain", "")
        category = item.get("category", "unknown")
        if category not in VALID_CATEGORIES:
            category = "unknown"
        results[domain] = {
            "category": category,
            "confidence": min(100, max(0, int(item.get("confidence", 50)))),
            "reasoning": str(item.get("reasoning", "")),
        }

    for domain, _ in batch:
        if domain not in results:
            results[domain] = {"category": "unknown", "confidence": 0, "reasoning": "No result from LLM"}

    return results


def reset_unknown_cache(domains: list[str] | None = None) -> int:
    """Remove LLM-cached entries that classify_domains won't actually apply.

    Clears entries where category is 'unknown' or 'personal' (both excluded from
    classify_domains overrides), so they'll be re-sent to the LLM next classify run.

    Args:
        domains: if given, only remove those specific domains; otherwise remove
                 all non-actionable cached entries.

    Returns:
        number of entries deleted
    """
    cache = _load_cache_key("llm_classifications")
    if domains is not None:
        to_delete = [d for d in domains if d in cache]
    else:
        to_delete = [d for d, v in cache.items() if v.get("category") in ("unknown", "personal")]
    for d in to_delete:
        del cache[d]
    _save_cache_key("llm_classifications", cache)
    return len(to_delete)


def set_manual_classification(domain: str, category: str) -> None:
    cache = _load_cache_key("manual_classifications")
    cache[domain] = {"category": category, "confidence": 100, "reasoning": "manual override"}
    _save_cache_key("manual_classifications", cache)


def clear_manual_classification(domain: str) -> None:
    cache = _load_cache_key("manual_classifications")
    if domain in cache:
        del cache[domain]
        _save_cache_key("manual_classifications", cache)


# ── Status / health ────────────────────────────────────────────────────────


def _record_status(up: bool, latency_ms: int | None = None, error: str | None = None) -> None:
    with _status_lock:
        prev_up = _status_cache.get("up")
        _status_cache["up"] = up
        _status_cache["last_latency_ms"] = latency_ms
        _status_cache["last_checked"] = time.time()
        _status_cache["error"] = error
        _status_cache["model"] = LLM_MODEL
        _status_cache["warming_up"] = False
        changed = prev_up != up
    if changed:
        try:
            from events import publish
            publish("llm.status", _public_status())
        except Exception:
            pass


def _public_status() -> dict:
    with _status_lock:
        s = dict(_status_cache)
    s["base_url"] = LLM_BASE_URL
    return s


def check_status(probe: bool = True) -> dict:
    """Return cached status; if probe=True, hit the endpoint when stale (>30s)."""
    with _status_lock:
        age = time.time() - _status_cache["last_checked"]
        cached = dict(_status_cache)
    if not probe or (cached["up"] is not None and age < 30):
        return _public_status()

    # Cheap probe — most LiteLLM proxies expose /v1/models
    req = urllib.request.Request(f"{LLM_BASE_URL}/models", method="GET")
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read(1)
        _record_status(up=True, latency_ms=int((time.time() - t0) * 1000), error=None)
    except Exception as e:
        _record_status(up=False, error=str(e))
    return _public_status()


def signal_warming() -> None:
    """Mark status as warming up — useful before kicking off a classify so UI can react."""
    with _status_lock:
        _status_cache["warming_up"] = True
        _status_cache["model"] = LLM_MODEL
    try:
        from events import publish
        publish("llm.status", _public_status())
    except Exception:
        pass
