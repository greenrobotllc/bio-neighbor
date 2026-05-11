#!/usr/bin/env python3
"""
Command-line version of the BioNeighbor Treatment Auditor (issue #62).

Mirrors the macOS app's `runDeepAudit()` orchestration
(macos_app/BioNeighbor/BioNeighbor/TreatmentAuditorView.swift) by hitting the
same Flask v2 routes the GUI uses, so audits can be regression-tested without
the UI in the loop. Pure stdlib — no `pip install` required.

Usage:
    python treatment_auditor_cli.py --plan examples/treatment_auditor_plan.example.json
    python treatment_auditor_cli.py --plan plan.json --format text
    python treatment_auditor_cli.py --plan plan.json --with-ollama --output audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BACKEND = "http://127.0.0.1:5000"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"

MODALITIES = ("radiation", "surgery", "chemotherapy", "targeted")
ALLOWED_SEVERITIES = ("mild", "moderate", "severe")
ALL_STEPS = ("pdq", "modality", "rxnorm", "interactions", "targets", "faers", "drug-trials")

REPORT_PDF_PATH = "/cancer-research/v2/treatment-auditor/report.pdf"


class CLIError(Exception):
    """Fatal CLI error — exits with a non-zero status."""


# --- HTTP helpers -----------------------------------------------------------

def _validate_url_scheme(url: str, arg_name: str) -> None:
    """Reject non-http(s) URLs early so urllib.request can't be coerced into
    file://, ftp://, or data: fetches by a typo or hostile config."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise CLIError(
            f"{arg_name} must use http:// or https:// "
            f"(got {parsed.scheme or '(no)'} scheme in {url!r})"
        )


def _http_request(
    method: str,
    url: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Tuple[int, Dict[str, Any]]:
    """Issue an HTTP request and decode the JSON response.

    Returns (status_code, parsed_body). Raises CLIError only on transport
    failures the caller can't recover from. Non-2xx responses with a JSON body
    are returned to the caller so route-specific error handling (e.g., PDQ
    404 with reason=pdq_unavailable) can run.
    """
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read() or b""
        status = e.code
    except urllib.error.URLError as e:
        raise CLIError(f"network error contacting {url}: {e.reason}") from None
    except TimeoutError:
        raise CLIError(f"timeout contacting {url}") from None

    if not raw:
        return status, {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise CLIError(f"non-JSON response from {url}: {e}") from None
    if not isinstance(parsed, dict):
        raise CLIError(f"unexpected JSON shape from {url} (not an object)")
    return status, parsed


# --- progress reporting -----------------------------------------------------

class Progress:
    """Per-step progress reporter + structured step log.

    The structured log is what the PDF report's "Audit pipeline log" section
    consumes (issue #67) — it mirrors what `TreatmentAuditorView.swift` shows
    on screen as the audit runs. Every `start(...)`/`end(...)` pair appends
    one entry to `entries`, with `state` mapping CLI outcomes onto the four
    states the report renderer knows how to colour."""

    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self._step_start: Optional[float] = None
        self._step_label: Optional[str] = None
        self.entries: List[Dict[str, Any]] = []

    def start(self, label: str) -> None:
        self._step_label = label
        self._step_start = time.monotonic()
        if not self.quiet:
            print(f"→ {label} …", end="", flush=True, file=sys.stderr)

    def end(self, outcome: str, detail: str = "") -> None:
        label = self._step_label or "?"
        # Map CLI outcome strings onto the report's state enum. "ok"/"done"
        # are equivalent — Swift uses .done, the CLI prints "ok".
        state = {
            "ok": "done",
            "done": "done",
            "skipped": "skipped",
            "failed": "failed",
        }.get(outcome, "done")
        self.entries.append({
            "label": label,
            "state": state,
            "detail": detail or None,
        })
        if not self.quiet:
            elapsed = time.monotonic() - (self._step_start or time.monotonic())
            suffix = f" ({detail})" if detail else ""
            print(f" {outcome} ({elapsed:.1f}s){suffix}", file=sys.stderr)
        self._step_start = None
        self._step_label = None


# --- plan validation --------------------------------------------------------

def _load_plan(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise CLIError(f"could not read plan file {path}: {e}") from None
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as e:
        raise CLIError(f"plan file {path} is not valid JSON: {e}") from None
    if not isinstance(plan, dict):
        raise CLIError(f"plan file {path} must contain a JSON object")
    return plan


def _validate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Validate / normalize plan fields. Returns a cleaned copy."""
    cleaned: Dict[str, Any] = {}

    if "cancer_type_id" in plan:
        val = plan["cancer_type_id"]
        if isinstance(val, bool) or not isinstance(val, int):
            raise CLIError("cancer_type_id must be an integer")
        cleaned["cancer_type_id"] = val
    if "cancer_type" in plan:
        if not isinstance(plan["cancer_type"], str) or not plan["cancer_type"].strip():
            raise CLIError("cancer_type must be a non-empty string")
        cleaned["cancer_type"] = plan["cancer_type"].strip()
    if "cancer_type_id" not in cleaned and "cancer_type" not in cleaned:
        raise CLIError("plan must include either cancer_type or cancer_type_id")

    if "subtype_id" in plan:
        val = plan["subtype_id"]
        if isinstance(val, bool) or not isinstance(val, int):
            raise CLIError("subtype_id must be an integer")
        cleaned["subtype_id"] = val
    if "subtype" in plan:
        if not isinstance(plan["subtype"], str) or not plan["subtype"].strip():
            raise CLIError("subtype must be a non-empty string")
        cleaned["subtype"] = plan["subtype"].strip()
    if "subtype_id" not in cleaned and "subtype" not in cleaned:
        raise CLIError("plan must include either subtype or subtype_id")

    stage = plan.get("stage", "")
    if stage is None:
        stage = ""
    if not isinstance(stage, str):
        raise CLIError("stage must be a string")
    cleaned["stage"] = stage.strip()

    stage_detail = plan.get("stage_detail", "")
    if stage_detail is None:
        stage_detail = ""
    if not isinstance(stage_detail, str):
        raise CLIError("stage_detail must be a string")
    cleaned["stage_detail"] = stage_detail.strip()

    drugs_raw = plan.get("drugs", [])
    if not isinstance(drugs_raw, list):
        raise CLIError('"drugs" must be a list')
    drugs: List[Dict[str, Any]] = []
    for i, entry in enumerate(drugs_raw):
        if not isinstance(entry, dict):
            raise CLIError(f"drugs[{i}] must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CLIError(f"drugs[{i}].name must be a non-empty string")
        chembl_id = entry.get("chembl_id")
        if chembl_id is not None and (not isinstance(chembl_id, str) or not chembl_id.strip()):
            raise CLIError(f"drugs[{i}].chembl_id must be a non-empty string or omitted")
        drugbank_id = entry.get("drugbank_id")
        if drugbank_id is not None and (not isinstance(drugbank_id, str) or not drugbank_id.strip()):
            raise CLIError(f"drugs[{i}].drugbank_id must be a non-empty string or omitted")
        drugs.append({
            "name": name.strip(),
            "chembl_id": chembl_id.strip() if isinstance(chembl_id, str) else None,
            "drugbank_id": drugbank_id.strip() if isinstance(drugbank_id, str) else None,
        })
    cleaned["drugs"] = drugs

    treatments_raw = plan.get("treatments", [])
    if not isinstance(treatments_raw, list):
        raise CLIError('"treatments" must be a list')
    treatments: List[str] = []
    for i, entry in enumerate(treatments_raw):
        if not isinstance(entry, str) or not entry.strip():
            raise CLIError(f"treatments[{i}] must be a non-empty string")
        treatments.append(entry.strip())
    cleaned["treatments"] = treatments

    symptoms_raw = plan.get("symptoms", [])
    if not isinstance(symptoms_raw, list):
        raise CLIError('"symptoms" must be a list')
    symptoms: List[Dict[str, str]] = []
    for i, entry in enumerate(symptoms_raw):
        if not isinstance(entry, dict):
            raise CLIError(f"symptoms[{i}] must be an object")
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            raise CLIError(f"symptoms[{i}].text must be a non-empty string")
        severity = entry.get("severity", "moderate")
        if severity not in ALLOWED_SEVERITIES:
            raise CLIError(
                f"symptoms[{i}].severity must be one of {ALLOWED_SEVERITIES}"
            )
        symptoms.append({"text": text.strip(), "severity": severity})
    cleaned["symptoms"] = symptoms

    return cleaned


# --- name resolution --------------------------------------------------------

def _resolve_taxonomy(
    backend: str,
    plan: Dict[str, Any],
    progress: Progress,
) -> Dict[str, Any]:
    """Resolve cancer_type / subtype to numeric IDs and display names.

    Always fetches the taxonomy so display names are populated for both the
    name-supplied and ID-supplied paths. When both IDs are supplied, also
    verifies the subtype belongs to the cancer type (the per-subtype list is
    scoped to its parent, so a subtype miss in that list = mismatch).
    """
    out = dict(plan)

    progress.start("resolving cancer type")
    status, body = _http_request("GET", f"{backend}/cancer-research/v2/cancer-types", timeout=10)
    if status != 200 or not body.get("success"):
        progress.end("failed", body.get("error", f"HTTP {status}"))
        raise CLIError("failed to list cancer types — backend reachable but route returned error")
    types = body.get("cancer_types") or []
    if "cancer_type_id" in out:
        match = next((t for t in types if t.get("id") == out["cancer_type_id"]), None)
        if not match:
            progress.end("failed", "id not found")
            raise CLIError(
                f"cancer_type_id {out['cancer_type_id']} not found in backend taxonomy"
            )
    else:
        match = _match_named(out["cancer_type"], types, ("name", "display_name"))
        if not match:
            progress.end("failed", "no match")
            raise CLIError(
                f"cancer_type {out['cancer_type']!r} did not match any of: "
                + ", ".join(t.get("display_name") or t.get("name") or str(t.get("id")) for t in types)
            )
        out["cancer_type_id"] = match["id"]
    out["cancer_type_display"] = match.get("display_name") or match.get("name")
    progress.end("ok", out["cancer_type_display"])

    progress.start("resolving subtype")
    status, body = _http_request(
        "GET",
        f"{backend}/cancer-research/v2/cancer-types/{out['cancer_type_id']}/subtypes",
        timeout=10,
    )
    if status != 200 or not body.get("success"):
        progress.end("failed", body.get("error", f"HTTP {status}"))
        raise CLIError("failed to list subtypes for cancer type")
    subtypes = body.get("subtypes") or []
    if "subtype_id" in out:
        match = next((s for s in subtypes if s.get("id") == out["subtype_id"]), None)
        if not match:
            progress.end("failed", "id mismatch")
            raise CLIError(
                f"subtype_id {out['subtype_id']} does not belong to "
                f"cancer_type_id {out['cancer_type_id']}"
            )
    else:
        match = _match_named(out["subtype"], subtypes, ("name", "short_name"))
        if not match:
            progress.end("failed", "no match")
            raise CLIError(
                f"subtype {out['subtype']!r} did not match any of: "
                + ", ".join(s.get("short_name") or s.get("name") or str(s.get("id")) for s in subtypes)
            )
        out["subtype_id"] = match["id"]
    out["subtype_display"] = match.get("short_name") or match.get("name")
    progress.end("ok", out["subtype_display"])

    return out


def _match_named(query: str, items: List[Dict[str, Any]], fields: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    q = query.strip().lower()
    for item in items:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and value.strip().lower() == q:
                return item
    matches: List[Dict[str, Any]] = []
    for item in items:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and q in value.strip().lower():
                if item not in matches:
                    matches.append(item)
                break
    return matches[0] if len(matches) == 1 else None


# --- pipeline steps ---------------------------------------------------------

def _step_pdq(backend: str, plan: Dict[str, Any], progress: Progress) -> Dict[str, Any]:
    progress.start("pdq")
    qs = {}
    if plan["stage"]:
        qs["stage"] = plan["stage"]
    if plan["stage_detail"]:
        qs["stage_detail"] = plan["stage_detail"]
    url = f"{backend}/cancer-research/v2/subtypes/{plan['subtype_id']}/treatment-summary"
    if qs:
        url += "?" + urllib.parse.urlencode(qs)
    try:
        status, body = _http_request("GET", url, timeout=20)
    except CLIError as e:
        progress.end("failed", str(e))
        return {"ok": False, "error": str(e)}

    if status == 404 and body.get("reason") == "pdq_unavailable":
        progress.end("skipped", body.get("error", "pdq unavailable"))
        return {
            "ok": True,
            "skipped": True,
            "reason": "pdq_unavailable",
            "cancer_type": body.get("cancer_type"),
        }
    if status != 200 or not body.get("success"):
        err = body.get("error", f"HTTP {status}")
        progress.end("failed", err)
        return {"ok": False, "error": err}

    progress.end("ok", f"{len(body.get('sections') or [])} sections")
    return {
        "ok": True,
        "skipped": False,
        "data": {
            "slug": body.get("slug"),
            "source_url": body.get("source_url"),
            "stage": body.get("stage"),
            "stage_detail": body.get("stage_detail"),
            "sections": body.get("sections") or [],
        },
    }


def _fetch_modality(
    backend: str,
    subtype_id: int,
    modality: str,
    limit: int,
    stage: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    params = {"modality": modality, "limit": str(limit)}
    if stage:
        params["stage"] = stage
    qs = urllib.parse.urlencode(params)
    url = f"{backend}/cancer-research/v2/subtypes/{subtype_id}/modality-trials?{qs}"
    try:
        status, body = _http_request("GET", url, timeout=30)
    except CLIError as e:
        return modality, {"ok": False, "error": str(e), "trials": []}
    if status != 200 or not body.get("success"):
        return modality, {"ok": False, "error": body.get("error", f"HTTP {status}"), "trials": []}
    return modality, {"ok": True, "trials": body.get("trials") or [], "condition": body.get("condition")}


def _step_modality(backend: str, plan: Dict[str, Any], limit: int, progress: Progress) -> Dict[str, Any]:
    progress.start("modality trials x4")
    by_modality: Dict[str, Dict[str, Any]] = {}
    stage = plan.get("stage") or None
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_fetch_modality, backend, plan["subtype_id"], m, limit, stage)
            for m in MODALITIES
        ]
        for f in futures:
            modality, result = f.result()
            by_modality[modality] = result
    total = sum(len(v.get("trials") or []) for v in by_modality.values())
    failures = [m for m, v in by_modality.items() if not v.get("ok")]
    detail = f"{total} trials"
    if failures:
        detail += f", failed: {','.join(failures)}"
    overall_ok = all(v.get("ok") for v in by_modality.values())
    progress.end("ok" if overall_ok else "failed", detail)
    return {"ok": overall_ok, "by_modality": by_modality}


def _step_rxnorm(backend: str, drugs: List[Dict[str, Any]], progress: Progress) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "normalizations": [], "deduped_drugs": [], "merge_notes": []}
    progress.start("rxnorm normalize")
    payload = {"drugs": [{"name": d["name"], "chembl_id": d["chembl_id"]} for d in drugs]}
    try:
        status, body = _http_request(
            "POST",
            f"{backend}/cancer-research/v2/treatment-auditor/normalize-drugs",
            body=payload,
            timeout=30,
        )
    except CLIError as e:
        progress.end("failed", str(e))
        return {
            "ok": False,
            "error": str(e),
            "normalizations": [],
            "deduped_drugs": list(drugs),
            "merge_notes": [],
        }
    if status != 200 or not body.get("success"):
        err = body.get("error", f"HTTP {status}")
        progress.end("failed", err)
        return {
            "ok": False,
            "error": err,
            "normalizations": [],
            "deduped_drugs": list(drugs),
            "merge_notes": [],
        }
    normalizations = body.get("normalizations") or []

    deduped, merge_notes = _dedupe_by_group_key(drugs, normalizations)
    detail = f"{len(drugs)} → {len(deduped)}"
    progress.end("ok", detail)
    return {
        "ok": True,
        "normalizations": normalizations,
        "deduped_drugs": deduped,
        "merge_notes": merge_notes,
    }


def _dedupe_by_group_key(
    drugs: List[Dict[str, Any]],
    normalizations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collapse drugs that share an RxNorm group_key. First occurrence wins.

    Mirrors `normalizeAndDedupeDrugs` in TreatmentAuditorView.swift — when the
    backend returns no group_key for an entry (RxNorm miss) we fall back to
    name:<lowercased> so misses still appear as distinct rows.
    """
    by_input: Dict[str, Dict[str, Any]] = {}
    for n in normalizations:
        key = n.get("input_name")
        if isinstance(key, str):
            by_input[key] = n

    seen: Dict[str, Dict[str, Any]] = {}
    merge_notes: List[Dict[str, Any]] = []
    for drug in drugs:
        norm = by_input.get(drug["name"]) or {}
        group_key = norm.get("group_key") or f"name:{drug['name'].lower()}"
        if group_key in seen:
            kept = seen[group_key]
            merge_notes.append({
                "kept_name": kept["name"],
                "merged_name": drug["name"],
                "group_key": group_key,
                "ingredient": norm.get("ingredient_name") or norm.get("normalized_name"),
            })
            continue
        merged = dict(drug)
        if norm.get("normalized_name"):
            merged["normalized_name"] = norm["normalized_name"]
        if norm.get("ingredient_rxcui"):
            merged["ingredient_rxcui"] = norm["ingredient_rxcui"]
        # Carry the RxNorm-resolved ingredient name forward so downstream
        # name-keyed lookups (DDInter, openFDA FAERS) can use the active
        # ingredient instead of the salt form. Without this, "Ribociclib
        # Succinate" reaches DDInter as "ribociclib succinate" (no match)
        # and openFDA returns ~90 reports vs ~30k for the ingredient form.
        if norm.get("ingredient_name"):
            merged["ingredient_name"] = norm["ingredient_name"]
        merged["group_key"] = group_key
        seen[group_key] = merged
    return list(seen.values()), merge_notes


def _lookup_name(drug: Dict[str, Any]) -> str:
    """The name to use when looking a drug up in name-keyed external sources
    (DDInter, openFDA). Prefers the RxNorm-resolved ingredient — it's the
    same active drug across salt forms, brand names, and capitalisation
    variations the underlying source would otherwise miss. Falls back to
    the user's original input when RxNorm didn't match."""
    return (drug.get("ingredient_name") or drug.get("name") or "").strip()


def _step_drug_interactions(backend: str, drugs: List[Dict[str, Any]], progress: Progress) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "drugbank_loaded": False, "matched": [], "interactions": [], "unmatched": []}
    progress.start("drug interactions")
    payload = {
        "drugs": [
            {
                "name": _lookup_name(d),
                "chembl_id": d.get("chembl_id"),
            }
            for d in drugs
        ]
    }
    try:
        status, body = _http_request(
            "POST",
            f"{backend}/cancer-research/v2/treatment-auditor/drug-interactions",
            body=payload,
            timeout=15,
        )
    except CLIError as e:
        progress.end("failed", str(e))
        return {"ok": False, "error": str(e)}
    if status != 200 or not body.get("success"):
        err = body.get("error", f"HTTP {status}")
        progress.end("failed", err)
        return {"ok": False, "error": err}
    interactions = body.get("interactions") or []
    drugbank_loaded = bool(body.get("drugbank_loaded"))
    if drugbank_loaded:
        progress.end("ok", f"{len(interactions)} interactions")
    else:
        # Without DDInter loaded the response is "data unavailable", not
        # "no interactions found". Logging "0 interactions" would conflate
        # the two for the pipeline log readers.
        progress.end("skipped", "DDInter not loaded")
    return {
        "ok": True,
        "drugbank_loaded": drugbank_loaded,
        "matched": body.get("matched") or [],
        "interactions": interactions,
        "unmatched": body.get("unmatched") or [],
    }


def _step_target_overlap(backend: str, drugs: List[Dict[str, Any]], progress: Progress) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "targets_by_drug": [], "overlaps": [], "unmatched": []}
    progress.start("target overlap")
    payload = {"drugs": [{"name": _lookup_name(d), "chembl_id": d.get("chembl_id")} for d in drugs]}
    try:
        status, body = _http_request(
            "POST",
            f"{backend}/cancer-research/v2/treatment-auditor/target-overlap",
            body=payload,
            timeout=60,
        )
    except CLIError as e:
        progress.end("failed", str(e))
        return {"ok": False, "error": str(e)}
    if status != 200 or not body.get("success"):
        err = body.get("error", f"HTTP {status}")
        progress.end("failed", err)
        return {"ok": False, "error": err}
    overlaps = body.get("overlaps") or []
    progress.end("ok", f"{len(overlaps)} overlaps")
    return {
        "ok": True,
        "targets_by_drug": body.get("targets_by_drug") or [],
        "overlaps": overlaps,
        "unmatched": body.get("unmatched") or [],
    }


def _step_faers(
    backend: str,
    drugs: List[Dict[str, Any]],
    symptoms: List[Dict[str, str]],
    progress: Progress,
) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "per_drug": [], "symptom_matches": []}
    progress.start("faers")
    payload = {
        "drugs": [{"name": _lookup_name(d), "chembl_id": d.get("chembl_id")} for d in drugs],
        "symptoms": [s["text"] for s in symptoms],
    }
    try:
        status, body = _http_request(
            "POST",
            f"{backend}/cancer-research/v2/treatment-auditor/adverse-events",
            body=payload,
            timeout=60,
        )
    except CLIError as e:
        progress.end("failed", str(e))
        return {"ok": False, "error": str(e)}
    if status != 200 or not body.get("success"):
        err = body.get("error", f"HTTP {status}")
        progress.end("failed", err)
        return {"ok": False, "error": err}
    matches = body.get("symptom_matches") or []
    progress.end("ok", f"{len(matches)} symptom matches")
    return {
        "ok": True,
        "per_drug": body.get("per_drug") or [],
        "symptom_matches": matches,
    }


def _fetch_drug_trials(
    backend: str,
    chembl_id: str,
    limit: int,
    condition: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    params = {"limit": str(limit)}
    if condition:
        params["condition"] = condition
    qs = urllib.parse.urlencode(params)
    safe_id = urllib.parse.quote(chembl_id, safe="")
    url = f"{backend}/cancer-research/v2/drugs/{safe_id}/trials?{qs}"
    try:
        status, body = _http_request("GET", url, timeout=30)
    except CLIError as e:
        return chembl_id, {"ok": False, "error": str(e), "trials": []}
    if status != 200 or not body.get("success"):
        return chembl_id, {"ok": False, "error": body.get("error", f"HTTP {status}"), "trials": []}
    return chembl_id, {"ok": True, "trials": body.get("trials") or []}


def _step_drug_trials(
    backend: str,
    drugs: List[Dict[str, Any]],
    limit: int,
    progress: Progress,
    condition: Optional[str] = None,
) -> Dict[str, Any]:
    with_chembl = [d for d in drugs if d.get("chembl_id")]
    skipped = [d["name"] for d in drugs if not d.get("chembl_id")]
    if not with_chembl:
        return {"ok": True, "by_drug": {}, "skipped_no_chembl_id": skipped}
    progress.start(f"drug trials x{len(with_chembl)}")
    by_drug: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(with_chembl))) as pool:
        futures = [
            pool.submit(_fetch_drug_trials, backend, d["chembl_id"], limit, condition)
            for d in with_chembl
        ]
        for f in futures:
            chembl_id, result = f.result()
            by_drug[chembl_id] = result
    total = sum(len(v.get("trials") or []) for v in by_drug.values())
    failures = [cid for cid, v in by_drug.items() if not v.get("ok")]
    detail = f"{total} trials"
    if failures:
        detail += f", failed: {','.join(failures)}"
    overall_ok = all(v.get("ok") for v in by_drug.values())
    progress.end("ok" if overall_ok else "failed", detail)
    return {"ok": overall_ok, "by_drug": by_drug, "skipped_no_chembl_id": skipped}


# --- Ollama multi-pass synthesis (optional) --------------------------------
#
# Verbatim port of OllamaService.swift's two-stage pipeline:
#   Stage 1: one mini-summary per non-empty source (PDQ, each modality, each
#            drug with trials) — 120-180 word digests.
#   Stage 2: one final synthesis that consumes the mini-summaries plus the
#            deterministic findings (DDInter / ChEMBL target / FAERS) — 350-550
#            word audit with NCT citations and a "Further reading" block.
# Prompt copy is held identical to the Swift side (OllamaService.swift:413-499)
# so CLI PDFs match the macOS app's output for the same inputs.


def _ollama_generate(
    endpoint: str,
    model: str,
    prompt: str,
    timeout: float = 600.0,
    stream_to_stderr: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    """One Ollama `POST /api/generate` call. Returns (ok, text, error)."""
    payload = {"model": model, "prompt": prompt, "stream": True}
    url = endpoint.rstrip("/") + "/api/generate"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chunks: List[str] = []
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    return False, "".join(chunks), str(obj["error"])
                piece = obj.get("response")
                if isinstance(piece, str) and piece:
                    chunks.append(piece)
                    if stream_to_stderr:
                        sys.stderr.write(piece)
                        sys.stderr.flush()
                if obj.get("done"):
                    break
        if stream_to_stderr:
            sys.stderr.write("\n")
        return True, "".join(chunks), None
    except urllib.error.URLError as e:
        return False, "", f"could not reach Ollama at {url}: {e.reason}"
    except TimeoutError:
        return False, "", f"timeout contacting Ollama at {url}"


def _plan_context_summary(plan: Dict[str, Any]) -> str:
    """Mirrors OllamaService.planContextSummary — patient-plan block reused
    verbatim in every mini-summary call. Deliberately omits deterministic
    findings (those go into the final synthesis only)."""
    lines: List[str] = []
    cancer = plan.get("cancer_type_display") or plan.get("cancer_type") or ""
    if cancer:
        lines.append(f"Cancer: {cancer}")
    subtype = plan.get("subtype_display") or plan.get("subtype")
    if subtype:
        lines.append(f"Subtype: {subtype}")
    markers = plan.get("subtype_markers") or []
    if markers:
        lines.append(f"Markers: {', '.join(markers)}")
    stage = plan.get("stage")
    if stage:
        lines.append(f"Stage: {stage}")
    detail = plan.get("stage_detail")
    if detail:
        lines.append(f"Stage detail: {detail}")
    drugs = plan.get("drugs") or []
    if drugs:
        lines.append(f"Prescribed drugs: {', '.join(d['name'] for d in drugs)}")
    treatments = plan.get("treatments") or []
    if treatments:
        lines.append(f"Scheduled treatments: {'; '.join(treatments)}")
    symptoms = plan.get("symptoms") or []
    if symptoms:
        formatted = []
        for s in symptoms:
            text = s.get("text", "")
            sev = s.get("severity")
            formatted.append(f"{text} ({sev})" if sev else text)
        lines.append(f"Symptoms / side effects: {'; '.join(formatted)}")
    return "\n".join(lines)


def _deterministic_findings_summary(report: Dict[str, Any]) -> str:
    """Mirrors OllamaService.deterministicFindingsSummary. Operates on the
    wire-format `report` (DDInter/target-overlap/FAERS already flattened),
    not the raw CLI step shape.

    Always emits a status line for each deterministic check (DDInter,
    target overlap) regardless of outcome — three distinct states (data
    unavailable / checked-none-found / findings present) so the LLM has
    explicit input. Without the "checked, none found" line, the model
    silently falls back to 'the plan does not provide information' for
    sections 4-5 of the synthesis, which falsely implies the user
    forgot to supply data."""
    lines: List[str] = []

    # DDInter pairwise drug-drug interactions
    interactions = report.get("drug_interactions") or []
    available = report.get("drug_interaction_data_available", True)
    if not available:
        lines.append("Drug-drug interaction data: unavailable (DDInter not loaded server-side).")
    elif interactions:
        lines.append("Known pairwise drug-drug interactions (DDInter):")
        for r in interactions:
            sev = r.get("severity") or "unknown"
            desc = r.get("description") or ""
            lines.append(f"- {r.get('drug_a', '')} ↔ {r.get('drug_b', '')} [severity: {sev}]: {desc}")
    else:
        lines.append(
            "Pairwise drug-drug interactions (DDInter): checked, "
            "no interactions found among the prescribed drugs."
        )

    # ChEMBL mechanism / target overlap
    overlaps = report.get("target_overlaps") or []
    if overlaps:
        lines.append("Mechanism/target overlap among prescribed drugs (ChEMBL):")
        for r in overlaps:
            target = r.get("gene_symbol") or r.get("protein_name") or "shared target"
            action_a = r.get("action_type_a") or "?"
            action_b = r.get("action_type_b") or "?"
            lines.append(
                f"- {r.get('drug_a', '')} ({action_a}) and "
                f"{r.get('drug_b', '')} ({action_b}) both act on {target}."
            )
    else:
        lines.append(
            "Mechanism/target overlap (ChEMBL): checked, "
            "no shared targets found among the prescribed drugs."
        )
    matches = report.get("faers_symptom_matches") or []
    if matches:
        lines.append("OpenFDA FAERS post-market reporting matches (symptom → top reaction term):")
        for r in matches:
            rank = r.get("rank_in_top")
            rank_snippet = f"#{rank} of top reactions, " if rank is not None else ""
            lines.append(
                f"- {r.get('drug_name', '')}: \"{r.get('symptom', '')}\" ↔ "
                f"\"{r.get('matched_term', '')}\" — {rank_snippet}"
                f"{r.get('count', 0)} reports out of {r.get('total_reports', 0)} total for this drug."
            )
    return "\n".join(lines)


def _build_source_summary_prompt(source_label: str, source_body: str, plan_context: str) -> str:
    return "\n".join([
        "You are summarizing one evidence source for a multi-source cancer treatment audit.",
        "Be concise and factual. Do not invent data — only summarize what's in the source below.",
        "",
        "== Patient plan (for relevance) ==",
        plan_context,
        "",
        f"== Source: {source_label} ==",
        source_body,
        "",
        "Write a 120-180 word digest covering:",
        "- What this source says that's relevant to *this* patient's subtype/stage.",
        "- Specific findings worth surfacing in the final audit (cite NCT IDs if the source is trial data, or section titles if it's a guideline/PDQ).",
        "- Anything notably missing — modalities or drug classes the source mentions that the patient's plan doesn't include.",
        "",
        "Plain prose, no preamble, no headings.",
    ])


def _build_synthesis_prompt(
    plan: Dict[str, Any],
    source_summaries: List[Dict[str, str]],
    deterministic_findings: str,
    pdq_source_url: Optional[str],
) -> str:
    lines: List[str] = []
    lines.append("You are writing the final audit of a cancer treatment plan, drawing on per-source summaries already produced.")
    lines.append("Be specific. Cite NCT IDs and the PDQ source URL inline when the answer rests on those sources. Use plain English. Flag uncertainty when evidence is thin. Do not invent trials, NCT IDs, or guidelines.")
    lines.append("")
    lines.append("== Patient plan ==")
    lines.append(_plan_context_summary(plan))
    lines.append("")
    if deterministic_findings:
        lines.append("== Deterministic findings ==")
        lines.append(deterministic_findings)
        lines.append("")
    if pdq_source_url:
        lines.append("== Citation hint ==")
        lines.append(f"PDQ source URL (use this when citing standard-of-care text): {pdq_source_url}")
        lines.append("")
    lines.append(f"== Per-source summaries ({len(source_summaries)}) ==")
    if not source_summaries:
        lines.append("(none — proceed with caution and explicitly note the lack of supporting evidence)")
    else:
        for entry in source_summaries:
            lines.append(f"--- {entry.get('label', '')} ---")
            lines.append(entry.get("summary", ""))
            lines.append("")
    lines.append("")
    lines.append("Write a treatment-plan audit (400-650 words) addressing, in numbered sections:")
    lines.append("Use plain text and Unicode characters only — do NOT emit LaTeX math (no $\\leftrightarrow$, no $\\to$, etc.). The arrow character ↔ is fine to use as-is when restating the deterministic findings.")
    lines.append("1. Efficacy signals: do the listed drugs have positive trial evidence in this subtype/stage? Cite NCT IDs.")
    lines.append("2. Alternative or adjunct regimens: across the modality summaries (radiation / surgery / chemotherapy / targeted), what trial arms showed clearly better outcomes than drug-only approaches? Compare drug-only vs drug+modality arms when the summaries surface them. Cite NCT IDs.")
    lines.append("3. Symptom & side-effect concerns: any of the patient's symptoms/side effects notably associated with the listed drugs? If the plan section above includes OpenFDA FAERS reaction matches, restate the top one or two specifically (drug, symptom→term, rank, raw counts). Frame these as post-market reporting (association, not causation) — do NOT invent counts.")
    lines.append("4. Drug-drug interactions: restate exactly what the deterministic findings block above says about drug-drug interactions. If it lists DDInter pairwise interactions, restate them verbatim and prioritize Major-severity ones for the prescriber. If it says 'checked, no interactions found', say that explicitly — the audit checked DDInter and no concerning pairs surfaced; do NOT say 'the plan does not provide information.' If it says interaction data was unavailable, say that. Do NOT invent interactions.")
    lines.append("5. Mechanism overlap: restate exactly what the deterministic findings block above says about target overlap. If it lists shared targets, briefly note whether that's likely intentional combination therapy (e.g. CDK4/6 + AI in HR+ breast cancer) or potentially redundant. If it says 'checked, no shared targets found', say that explicitly — the audit checked ChEMBL and no overlap surfaced; do NOT say 'the plan does not provide information.' Do NOT invent overlaps.")
    lines.append("6. Surgical & radiation considerations: address surgery and radiation explicitly when they are part of standard of care for this subtype/stage (use the PDQ summary as the authoritative source — surgery is primary for most early-stage solid tumours including breast, colon, and many lung cancers). Comment on: (a) whether the patient's plan includes the surgical/radiation steps PDQ identifies as standard, (b) timing and sequencing relative to the listed systemic therapy (neoadjuvant vs adjuvant), (c) lymph node assessment when applicable, and (d) any scheduled surgical or radiation treatments the patient supplied — name each one and comment on PDQ alignment. If PDQ doesn't cover surgical/radiation guidance for this cancer (hematologic / advanced metastatic / unmapped), say so. Use \"discuss with your surgical oncologist / radiation oncologist\" framing.")
    lines.append("7. Plan gaps: drug classes AND treatment modalities the standard of care for this subtype/stage typically includes that aren't in the plan. Use the PDQ summary as the authoritative source for SOC framing. Use \"discuss with your oncology team\" language.")
    lines.append("8. Uncertainty: where is evidence thin? What would you ask the oncology team?")
    lines.append("")
    lines.append("Then add a final \"Further reading\" block listing:")
    if pdq_source_url:
        lines.append(f"- NCI PDQ summary: {pdq_source_url}")
    lines.append("- Up to 3 key NCT IDs from the summaries above, formatted as https://clinicaltrials.gov/study/{NCT}.")
    lines.append("")
    lines.append("End with EXACTLY this line as the final line:")
    lines.append("Not medical advice. Discuss any plan changes with your oncologist.")
    return "\n".join(lines)


def _compress_pdq(pdq: Dict[str, Any]) -> str:
    """Mirrors OllamaService.compressPDQ — prompt-ready text body for one PDQ
    summary, with the source URL up top so the model can cite it."""
    lines: List[str] = []
    slug = (pdq.get("slug") or "").capitalize()
    lines.append(f"NCI PDQ — {slug} (Health Professional)")
    lines.append(f"Source URL: {pdq.get('source_url', '')}")
    if pdq.get("stage"):
        lines.append(f"Filtered for stage: {pdq['stage']}")
    if pdq.get("stage_detail"):
        lines.append(f"Stage detail filter: {pdq['stage_detail']}")
    lines.append("")
    for section in pdq.get("sections") or []:
        title = section.get("title", "")
        lines.append(f"### {title}")
        parent = section.get("parent")
        if parent and parent != title:
            lines.append(f"(under: {parent})")
        text = section.get("text") or ""
        if text:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _compress_trials(trials: List[Dict[str, Any]], header: str) -> str:
    """Mirrors OllamaService.compressTrials — capped at 6 trials to bound
    prompt size; backend already orders most-informative first."""
    lines: List[str] = []
    lines.append(header)
    plural = "" if len(trials) == 1 else "s"
    lines.append(f"{len(trials)} trial{plural} below.")
    lines.append("")
    for trial in trials[:6]:
        lines.append(f"NCT: {trial.get('nct_id', '')}")
        if trial.get("title"):
            lines.append(f"  Title: {trial['title']}")
        if trial.get("status"):
            lines.append(f"  Status: {trial['status']}")
        phases = trial.get("phase") or []
        if phases:
            lines.append(f"  Phase: {', '.join(phases)}")
        arms = trial.get("arms") or []
        if arms:
            lines.append("  Arms:")
            for arm in arms:
                label = arm.get("label") or "—"
                interventions = " + ".join(arm.get("interventions") or [])
                lines.append(f"    - {label}: {interventions}")
        outcomes = trial.get("primary_outcomes") or []
        if outcomes:
            lines.append("  Primary outcomes:")
            for outcome in outcomes:
                title = outcome.get("title") or "(unnamed)"
                unit = f" [{outcome['unit']}]" if outcome.get("unit") else ""
                lines.append(f"    • {title}{unit}")
                for r in outcome.get("arm_results") or []:
                    arm_label = r.get("arm_label") or "?"
                    val = r.get("value") or "?"
                    lines.append(f"      {arm_label}: {val}")
        elif not trial.get("has_results"):
            lines.append("  Results: not yet reported")
        lines.append("")
    return "\n".join(lines)


def _build_report_payload(
    plan: Dict[str, Any],
    steps: Dict[str, Any],
    step_log: List[Dict[str, Any]],
    *,
    source_summaries: Optional[List[Dict[str, str]]] = None,
    final_audit: Optional[str] = None,
) -> Dict[str, Any]:
    """Translate the CLI's internal `result` into the wire format the
    `/treatment-auditor/report.pdf` endpoint expects (issue #67). The CLI's
    step shape is shaped for diffing/regression tests; the wire format is
    what both Swift and the report builder agree on, with field names
    matching `TreatmentAuditPlan` in OllamaService.swift."""
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": {
            "cancer_type": plan.get("cancer_type"),
            "cancer_type_id": plan.get("cancer_type_id"),
            "cancer_type_display": plan.get("cancer_type_display"),
            "subtype": plan.get("subtype"),
            "subtype_id": plan.get("subtype_id"),
            "subtype_display": plan.get("subtype_display"),
            "subtype_markers": plan.get("subtype_markers") or [],
            "stage": plan.get("stage") or "",
            "stage_detail": plan.get("stage_detail") or "",
            "drugs": [
                {"name": d["name"], "chembl_id": d.get("chembl_id")}
                for d in plan.get("drugs", [])
            ],
            "treatments": list(plan.get("treatments") or []),
            "symptoms": [
                {"text": s["text"], "severity": s.get("severity")}
                for s in plan.get("symptoms") or []
            ],
        },
        "steps": list(step_log),
    }

    rxnorm = steps.get("rxnorm") or {}
    merge_notes_raw = rxnorm.get("merge_notes") or []
    # Group pairwise (kept, merged) entries onto one row per ingredient so
    # the report shows "Herceptin + Trastuzumab → trastuzumab" once rather
    # than three rows when three brand variants collapse onto one ingredient.
    grouped: Dict[str, Dict[str, Any]] = {}
    for note in merge_notes_raw:
        key = note.get("group_key") or note.get("kept_name") or ""
        if not key:
            continue
        bucket = grouped.setdefault(key, {
            "original_names": [],
            "ingredient_name": note.get("ingredient") or note.get("kept_name") or "",
        })
        for name in (note.get("kept_name"), note.get("merged_name")):
            if name and name not in bucket["original_names"]:
                bucket["original_names"].append(name)
    payload["merge_notes"] = list(grouped.values())

    pdq = steps.get("pdq") or {}
    if pdq.get("ok") and pdq.get("data"):
        data = pdq["data"]
        payload["pdq_summary"] = {
            "slug": data.get("slug"),
            "source_url": data.get("source_url"),
            "stage": data.get("stage"),
            "stage_detail": data.get("stage_detail"),
            "sections": list(data.get("sections") or []),
        }

    modality = steps.get("modality_trials") or {}
    by_modality = modality.get("by_modality") or {}
    payload["modality_trials"] = [
        {
            "modality": m,
            "condition": (by_modality.get(m) or {}).get("condition"),
            "trials": (by_modality.get(m) or {}).get("trials") or [],
        }
        for m in MODALITIES if m in by_modality
    ]

    drug_trials = steps.get("drug_trials") or {}
    by_drug = drug_trials.get("by_drug") or {}
    deduped_drugs = rxnorm.get("deduped_drugs") or plan.get("drugs", [])
    payload["drug_trials"] = []
    for drug in deduped_drugs:
        chembl_id = drug.get("chembl_id")
        entry = by_drug.get(chembl_id) if chembl_id else None
        payload["drug_trials"].append({
            "drug_name": drug["name"],
            "chembl_id": chembl_id,
            "trials": (entry or {}).get("trials") or [],
        })

    interactions = steps.get("drug_interactions") or {}
    payload["drug_interaction_data_available"] = bool(interactions.get("drugbank_loaded", True)) if interactions.get("ok") else interactions.get("drugbank_loaded", True)
    payload["drug_interactions"] = [
        {
            "drug_a": r.get("drug_a_name") or r.get("drug_a"),
            "drug_b": r.get("drug_b_name") or r.get("drug_b"),
            "severity": r.get("severity"),
            "description": r.get("description"),
        }
        for r in (interactions.get("interactions") or [])
    ]

    target_overlap = steps.get("target_overlap") or {}
    overlaps_flat: List[Dict[str, Any]] = []
    for overlap in target_overlap.get("overlaps") or []:
        for shared in overlap.get("shared_targets") or []:
            overlaps_flat.append({
                "drug_a": overlap.get("drug_a"),
                "drug_b": overlap.get("drug_b"),
                "gene_symbol": shared.get("gene_symbol"),
                "protein_name": shared.get("protein_name"),
                "action_type_a": shared.get("action_type_a"),
                "action_type_b": shared.get("action_type_b"),
            })
    payload["target_overlaps"] = overlaps_flat

    faers = steps.get("adverse_events") or {}
    payload["faers_panels"] = list(faers.get("per_drug") or [])
    payload["faers_symptom_matches"] = list(faers.get("symptom_matches") or [])

    if source_summaries is not None:
        payload["source_summaries"] = source_summaries
    if final_audit is not None:
        payload["final_audit"] = final_audit

    return payload


def _post_pdf(backend: str, payload: Dict[str, Any], output: Path) -> None:
    """POST `payload` to /treatment-auditor/report.pdf and write the response
    bytes to `output`. Raises CLIError on transport / non-2xx response."""
    url = backend.rstrip("/") + REPORT_PDF_PATH
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/pdf"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
            if "application/pdf" not in content_type:
                raise CLIError(f"backend returned {content_type!r} from {url} (expected application/pdf)")
            output.write_bytes(body)
    except urllib.error.HTTPError as e:
        # Backend returns JSON on errors. Surface its message rather than the
        # raw HTML Flask emits for unexpected exceptions.
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err = err_body.get("error", f"HTTP {e.code}")
        except (ValueError, UnicodeDecodeError):
            err = f"HTTP {e.code}"
        raise CLIError(f"backend rejected {url}: {err}") from None
    except urllib.error.URLError as e:
        raise CLIError(f"network error contacting {url}: {e.reason}") from None
    except TimeoutError:
        raise CLIError(f"timeout contacting {url}") from None
    except OSError as e:
        raise CLIError(f"could not write {output}: {e}") from None


# LaTeX → Unicode replacements applied to LLM output. Some local models
# (notably gemma) reflexively emit LaTeX math notation when they see
# arrows in the prompt context, even after being told not to. The audit
# report renders Markdown-ish prose — LaTeX renders as literal `$\foo$`
# garbage. Strip the common cases as a defence-in-depth in case the
# prompt instruction is ignored.
_LATEX_REPLACEMENTS = (
    ("$\\leftrightarrow$", "↔"),
    ("$\\Leftrightarrow$", "↔"),
    ("$\\rightarrow$", "→"),
    ("$\\Rightarrow$", "→"),
    ("$\\to$", "→"),
    ("$\\leftarrow$", "←"),
    ("$\\Leftarrow$", "←"),
    ("$\\sim$", "~"),
    ("$\\approx$", "≈"),
    ("$\\le$", "≤"),
    ("$\\ge$", "≥"),
    ("$\\pm$", "±"),
    ("$\\times$", "×"),
    ("$\\alpha$", "α"),
    ("$\\beta$", "β"),
    ("$\\mu$", "μ"),
)


def _strip_latex(text: str) -> str:
    """Replace common LaTeX math escapes the LLM may emit despite being
    told not to. Targeted rather than regex-based so we don't accidentally
    munge dollar amounts or legitimate `\\X` strings the model produces."""
    if not text:
        return text
    for tex, unicode_char in _LATEX_REPLACEMENTS:
        text = text.replace(tex, unicode_char)
    return text


def _run_synthesis_pipeline(
    endpoint: str,
    model: str,
    plan: Dict[str, Any],
    report_payload: Dict[str, Any],
    progress: Progress,
) -> Tuple[List[Dict[str, str]], str, Optional[str]]:
    """Run the multi-pass synthesis. Returns (source_summaries, final_audit,
    error). On a per-source failure the source is skipped (not fatal).
    On final-synthesis failure, error is set and final_audit is whatever was
    streamed before the failure."""
    plan_context = _plan_context_summary(plan)
    source_summaries: List[Dict[str, str]] = []

    pdq = report_payload.get("pdq_summary")
    if pdq and pdq.get("sections"):
        slug = (pdq.get("slug") or "").capitalize()
        label = f"NCI PDQ — {slug}"
        body = _compress_pdq(pdq)
        progress.start(f"summarize {label}")
        ok, text, err = _ollama_generate(endpoint, model, _build_source_summary_prompt(label, body, plan_context))
        if ok:
            progress.end("ok", f"{len(text)} chars")
            source_summaries.append({"label": label, "summary": _strip_latex(text.strip())})
        else:
            progress.end("failed", err or "")

    for entry in report_payload.get("modality_trials") or []:
        trials = entry.get("trials") or []
        if not trials:
            continue
        modality = entry.get("modality", "").capitalize()
        condition = entry.get("condition")
        header = f"Modality: {modality} trials" + (f" — condition: {condition}" if condition else "")
        body = _compress_trials(trials, header)
        label = f"{modality} trials"
        progress.start(f"summarize {label}")
        ok, text, err = _ollama_generate(endpoint, model, _build_source_summary_prompt(label, body, plan_context))
        if ok:
            progress.end("ok", f"{len(text)} chars")
            source_summaries.append({"label": label, "summary": _strip_latex(text.strip())})
        else:
            progress.end("failed", err or "")

    for entry in report_payload.get("drug_trials") or []:
        trials = entry.get("trials") or []
        if not trials:
            continue
        drug_name = entry.get("drug_name", "")
        chembl_id = entry.get("chembl_id")
        header = f"Trials linked to {drug_name}" + (f" [{chembl_id}]" if chembl_id else "")
        body = _compress_trials(trials, header)
        label = f"{drug_name} trials"
        progress.start(f"summarize {label}")
        ok, text, err = _ollama_generate(endpoint, model, _build_source_summary_prompt(label, body, plan_context))
        if ok:
            progress.end("ok", f"{len(text)} chars")
            source_summaries.append({"label": label, "summary": _strip_latex(text.strip())})
        else:
            progress.end("failed", err or "")

    deterministic = _deterministic_findings_summary(report_payload)
    pdq_url = (pdq or {}).get("source_url") if pdq else None
    final_prompt = _build_synthesis_prompt(plan, source_summaries, deterministic, pdq_url)

    progress.start("synthesize final audit")
    ok, text, err = _ollama_generate(endpoint, model, final_prompt, stream_to_stderr=not progress.quiet)
    if ok:
        progress.end("ok", f"{len(text)} chars")
        return source_summaries, _strip_latex(text.strip()), None
    progress.end("failed", err or "")
    return source_summaries, _strip_latex(text.strip()), err


# --- text rendering ---------------------------------------------------------

def _render_text(result: Dict[str, Any]) -> str:
    out: List[str] = []
    plan = result["plan"]
    out.append("=" * 70)
    out.append("Treatment Auditor — CLI run")
    out.append("=" * 70)
    out.append(f"Cancer type: {plan.get('cancer_type_display') or plan.get('cancer_type')} (id={plan.get('cancer_type_id')})")
    out.append(f"Subtype:     {plan.get('subtype_display') or plan.get('subtype')} (id={plan.get('subtype_id')})")
    out.append(f"Stage:       {plan.get('stage') or '(unspecified)'} / {plan.get('stage_detail') or '(no detail)'}")
    out.append(f"Drugs:       {', '.join(d['name'] for d in plan.get('drugs', [])) or '(none)'}")
    out.append(f"Symptoms:    {', '.join(s['text'] + ':' + s['severity'] for s in plan.get('symptoms') or []) or '(none)'}")
    out.append("")

    steps = result["steps"]
    for key in ("pdq", "modality_trials", "rxnorm", "drug_interactions", "target_overlap", "adverse_events", "drug_trials"):
        s = steps.get(key)
        if s is None:
            continue
        out.append(f"--- {key} ---")
        if not s.get("ok"):
            out.append(f"  FAILED: {s.get('error')}")
            out.append("")
            continue
        if key == "pdq":
            if s.get("skipped"):
                out.append(f"  SKIPPED ({s.get('reason')}): {s.get('cancer_type')}")
            else:
                data = s.get("data") or {}
                out.append(f"  slug: {data.get('slug')}  source: {data.get('source_url')}")
                out.append(f"  sections: {len(data.get('sections') or [])}")
        elif key == "modality_trials":
            for modality, mr in (s.get("by_modality") or {}).items():
                count = len(mr.get("trials") or []) if mr.get("ok") else 0
                tag = "ok" if mr.get("ok") else f"failed: {mr.get('error')}"
                out.append(f"  {modality:14s} {count:3d} trials  [{tag}]")
        elif key == "rxnorm":
            out.append(f"  inputs: {len(s.get('normalizations') or [])}  deduped: {len(s.get('deduped_drugs') or [])}")
            for note in s.get("merge_notes") or []:
                out.append(f"    merged {note['merged_name']!r} into {note['kept_name']!r} ({note.get('ingredient') or note['group_key']})")
        elif key == "drug_interactions":
            interactions = s.get("interactions") or []
            out.append(f"  drugbank_loaded: {s.get('drugbank_loaded')}  interactions: {len(interactions)}")
            for inter in interactions[:10]:
                out.append(f"    {inter.get('drug_a_name')} + {inter.get('drug_b_name')} [{inter.get('severity')}]")
        elif key == "target_overlap":
            overlaps = s.get("overlaps") or []
            out.append(f"  pairwise overlaps: {len(overlaps)}  unmatched: {len(s.get('unmatched') or [])}")
            for ov in overlaps:
                shared = ov.get("shared_targets") or []
                names = ", ".join(t.get("gene_symbol") or t.get("target_chembl_id") or "?" for t in shared)
                out.append(f"    {ov.get('drug_a')} · {ov.get('drug_b')}: {names}")
        elif key == "adverse_events":
            out.append(f"  per_drug: {len(s.get('per_drug') or [])}  symptom_matches: {len(s.get('symptom_matches') or [])}")
            for m in s.get("symptom_matches") or []:
                out.append(f"    {m.get('drug_name')}: {m.get('symptom')} ↔ {m.get('matched_term')} (#{m.get('rank_in_top')}, {m.get('count')} reports)")
        elif key == "drug_trials":
            for chembl_id, tr in (s.get("by_drug") or {}).items():
                count = len(tr.get("trials") or []) if tr.get("ok") else 0
                tag = "ok" if tr.get("ok") else f"failed: {tr.get('error')}"
                out.append(f"  {chembl_id:14s} {count:3d} trials  [{tag}]")
            if s.get("skipped_no_chembl_id"):
                out.append(f"  (skipped — no chembl_id: {', '.join(s['skipped_no_chembl_id'])})")
        out.append("")

    if "source_summaries" in result:
        out.append("--- per-source summaries ---")
        for entry in result["source_summaries"] or []:
            out.append(f"[{entry.get('label', '')}]")
            out.append(entry.get("summary", "") or "(empty)")
            out.append("")
    if "final_audit" in result:
        out.append("--- final audit ---")
        text = result.get("final_audit") or ""
        if text:
            out.append(text)
        else:
            out.append("(empty)")
        if result.get("synthesis_error"):
            out.append(f"FAILED: {result['synthesis_error']}")
        out.append("")
    return "\n".join(out)


# --- main -------------------------------------------------------------------

def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="treatment_auditor_cli.py",
        description="Run the BioNeighbor Treatment Auditor pipeline from the command line (issue #62).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python treatment_auditor_cli.py --plan examples/treatment_auditor_plan.example.json\n"
        ),
    )
    parser.add_argument("--plan", required=True, type=Path, help="Path to JSON plan file.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help=f"Backend base URL (default: {DEFAULT_BACKEND}).")
    parser.add_argument("--format", choices=("json", "text"), default="json", help="Output format (default: json).")
    parser.add_argument("--output", type=Path, default=None, help="Write output to file instead of stdout.")
    parser.add_argument("--pdf", type=Path, default=None, help="Also render the audit as a PDF at this path (issue #67).")
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip the multi-pass Ollama synthesis (per-source mini-summaries + final audit). "
             "By default the synthesis runs to match the macOS app's behaviour.",
    )
    parser.add_argument("--ollama-endpoint", default=DEFAULT_OLLAMA, help=f"Ollama base URL (default: {DEFAULT_OLLAMA}).")
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL, help=f"Ollama model name (default: {DEFAULT_OLLAMA_MODEL}).")
    parser.add_argument("--modality-limit", type=int, default=8, help="Max trials per modality (default 8, max 20).")
    parser.add_argument("--drug-trials-limit", type=int, default=15, help="Max trials per drug (default 15).")
    parser.add_argument(
        "--skip",
        default="",
        help=f"Comma-separated steps to skip. Allowed: {','.join(ALL_STEPS)}.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-step progress on stderr.")
    return parser.parse_args(argv)


def _check_backend(backend: str) -> None:
    try:
        status, body = _http_request("GET", f"{backend}/cancer-research/v2/cancer-types", timeout=5)
    except CLIError as e:
        raise CLIError(
            f"backend at {backend} is unreachable: {e}\n"
            "Start the server with ./start_server.sh and retry."
        ) from None
    if status != 200 or not body.get("success"):
        raise CLIError(
            f"backend at {backend} returned HTTP {status}; cannot list cancer types. "
            "Confirm ./start_server.sh is running and the database is seeded."
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    skip_set = {s.strip() for s in args.skip.split(",") if s.strip()}
    bad = skip_set - set(ALL_STEPS)
    if bad:
        print(f"error: --skip got unknown step(s): {','.join(sorted(bad))}", file=sys.stderr)
        return 2

    if args.modality_limit < 1 or args.modality_limit > 20:
        print("error: --modality-limit must be between 1 and 20", file=sys.stderr)
        return 2
    if args.drug_trials_limit < 1 or args.drug_trials_limit > 50:
        print("error: --drug-trials-limit must be between 1 and 50", file=sys.stderr)
        return 2

    progress = Progress(quiet=args.quiet)
    backend = (args.backend or DEFAULT_BACKEND).rstrip("/")

    try:
        _validate_url_scheme(backend, "--backend")
        if not args.no_ollama:
            _validate_url_scheme(args.ollama_endpoint, "--ollama-endpoint")
        plan_raw = _load_plan(args.plan)
        plan = _validate_plan(plan_raw)
        _check_backend(backend)
        plan = _resolve_taxonomy(backend, plan, progress)
    except CLIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    steps: Dict[str, Any] = {}

    if "pdq" not in skip_set:
        steps["pdq"] = _step_pdq(backend, plan, progress)
    if "modality" not in skip_set:
        steps["modality_trials"] = _step_modality(backend, plan, args.modality_limit, progress)

    if "rxnorm" not in skip_set:
        rxnorm = _step_rxnorm(backend, plan["drugs"], progress)
    else:
        rxnorm = {"ok": True, "skipped_by_user": True, "deduped_drugs": list(plan["drugs"])}
    steps["rxnorm"] = rxnorm
    deduped_value = rxnorm.get("deduped_drugs")
    deduped = deduped_value if deduped_value is not None else list(plan["drugs"])

    if "interactions" not in skip_set:
        steps["drug_interactions"] = _step_drug_interactions(backend, deduped, progress)
    if "targets" not in skip_set:
        steps["target_overlap"] = _step_target_overlap(backend, deduped, progress)
    if "faers" not in skip_set:
        steps["adverse_events"] = _step_faers(backend, deduped, plan["symptoms"], progress)
    if "drug-trials" not in skip_set:
        # Pass the patient's cancer type so per-drug trial fetches filter
        # to indications matching the relevant cancer (issue #67 follow-up:
        # ribociclib has been studied in melanoma + glioma + breast; without
        # this filter the audit's per-drug summary surfaced off-subtype
        # trials for HR+ breast-cancer patients).
        cancer_condition = (
            plan.get("cancer_type_display") or plan.get("cancer_type") or ""
        ).strip() or None
        steps["drug_trials"] = _step_drug_trials(
            backend, deduped, args.drug_trials_limit, progress,
            condition=cancer_condition,
        )

    # Synthesis prompts and the report payload should reflect the deduped
    # drug list (after RxNorm collapsed brand→generic duplicates), otherwise
    # the LLM sees Herceptin AND Trastuzumab listed separately even though
    # they collapse to one ingredient. The user-visible audit trail of what
    # was merged is preserved via merge_notes in the report payload.
    effective_plan = dict(plan)
    effective_plan["drugs"] = list(deduped)

    result: Dict[str, Any] = {"plan": plan, "steps": steps}

    source_summaries: Optional[List[Dict[str, str]]] = None
    final_audit: Optional[str] = None
    synthesis_error: Optional[str] = None
    if not args.no_ollama:
        # Multi-pass synthesis needs the wire-format payload (PDQ + flattened
        # modality / drug trials) to drive its per-source pass, so we build
        # the payload once now and reuse it for the optional --pdf POST.
        payload_for_synth = _build_report_payload(effective_plan, steps, progress.entries)
        source_summaries, final_audit, synthesis_error = _run_synthesis_pipeline(
            args.ollama_endpoint,
            args.ollama_model,
            effective_plan,
            payload_for_synth,
            progress,
        )
        result["source_summaries"] = source_summaries
        result["final_audit"] = final_audit
        if synthesis_error:
            result["synthesis_error"] = synthesis_error

    if args.format == "json":
        rendered = json.dumps(result, indent=2)
    else:
        rendered = _render_text(result)

    if args.output:
        try:
            args.output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        except OSError as e:
            print(f"error: could not write {args.output}: {e}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")

    if args.pdf:
        progress.start("render PDF")
        try:
            payload = _build_report_payload(
                effective_plan,
                steps,
                progress.entries,
                source_summaries=source_summaries,
                final_audit=final_audit,
            )
            _post_pdf(backend, payload, args.pdf)
            progress.end("ok", str(args.pdf))
        except CLIError as e:
            progress.end("failed", str(e))
            print(f"error rendering PDF: {e}", file=sys.stderr)
            return 2

    pdq = steps.get("pdq", {})
    pdq_ok = "pdq" in skip_set or (pdq.get("ok") and (pdq.get("skipped") or pdq.get("data")))
    modality = steps.get("modality_trials", {})
    any_trials = any(
        v.get("ok") and v.get("trials") for v in (modality.get("by_modality") or {}).values()
    )
    drug_trials = steps.get("drug_trials", {})
    any_drug_trials = any(
        v.get("ok") and v.get("trials") for v in (drug_trials.get("by_drug") or {}).values()
    )
    return 0 if (pdq_ok and (any_trials or any_drug_trials or "modality" in skip_set or "drug-trials" in skip_set)) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
