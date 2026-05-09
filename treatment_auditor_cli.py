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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BACKEND = "http://127.0.0.1:5000"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"

MODALITIES = ("radiation", "surgery", "chemotherapy", "targeted")
ALLOWED_SEVERITIES = ("mild", "moderate", "severe")
ALL_STEPS = ("pdq", "modality", "rxnorm", "interactions", "targets", "faers", "drug-trials")


class CLIError(Exception):
    """Fatal CLI error — exits with a non-zero status."""


# --- HTTP helpers -----------------------------------------------------------

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
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self._step_start: Optional[float] = None
        self._step_label: Optional[str] = None

    def start(self, label: str) -> None:
        self._step_label = label
        self._step_start = time.monotonic()
        if not self.quiet:
            print(f"→ {label} …", end="", flush=True, file=sys.stderr)

    def end(self, outcome: str, detail: str = "") -> None:
        if self.quiet:
            self._step_start = None
            self._step_label = None
            return
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
        if not isinstance(plan["cancer_type_id"], int):
            raise CLIError("cancer_type_id must be an integer")
        cleaned["cancer_type_id"] = plan["cancer_type_id"]
    if "cancer_type" in plan:
        if not isinstance(plan["cancer_type"], str) or not plan["cancer_type"].strip():
            raise CLIError("cancer_type must be a non-empty string")
        cleaned["cancer_type"] = plan["cancer_type"].strip()
    if "cancer_type_id" not in cleaned and "cancer_type" not in cleaned:
        raise CLIError("plan must include either cancer_type or cancer_type_id")

    if "subtype_id" in plan:
        if not isinstance(plan["subtype_id"], int):
            raise CLIError("subtype_id must be an integer")
        cleaned["subtype_id"] = plan["subtype_id"]
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
    """Resolve cancer_type / subtype names to numeric IDs against the backend.

    No-ops when both *_id fields are present. Mutates a copy of `plan` to
    include resolved IDs and human-readable display names.
    """
    out = dict(plan)

    if "cancer_type_id" not in out:
        progress.start("resolving cancer type")
        status, body = _http_request("GET", f"{backend}/cancer-research/v2/cancer-types", timeout=10)
        if status != 200 or not body.get("success"):
            progress.end("failed", body.get("error", f"HTTP {status}"))
            raise CLIError("failed to list cancer types — backend reachable but route returned error")
        types = body.get("cancer_types") or []
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

    if "subtype_id" not in out:
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
    for item in items:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and q in value.strip().lower():
                return item
    return None


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


def _fetch_modality(backend: str, subtype_id: int, modality: str, limit: int) -> Tuple[str, Dict[str, Any]]:
    qs = urllib.parse.urlencode({"modality": modality, "limit": str(limit)})
    url = f"{backend}/cancer-research/v2/subtypes/{subtype_id}/modality-trials?{qs}"
    try:
        status, body = _http_request("GET", url, timeout=30)
    except CLIError as e:
        return modality, {"ok": False, "error": str(e), "trials": []}
    if status != 200 or not body.get("success"):
        return modality, {"ok": False, "error": body.get("error", f"HTTP {status}"), "trials": []}
    return modality, {"ok": True, "trials": body.get("trials") or [], "condition": body.get("condition")}


def _step_modality(backend: str, plan: Dict[str, Any], limit: int, progress: Progress) -> Dict[str, Any]:
    progress.start(f"modality trials ×4")
    by_modality: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_fetch_modality, backend, plan["subtype_id"], m, limit) for m in MODALITIES]
        for f in futures:
            modality, result = f.result()
            by_modality[modality] = result
    total = sum(len(v.get("trials") or []) for v in by_modality.values())
    failures = [m for m, v in by_modality.items() if not v.get("ok")]
    detail = f"{total} trials"
    if failures:
        detail += f", failed: {','.join(failures)}"
    progress.end("ok", detail)
    return {"ok": True, "by_modality": by_modality}


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
        merged["group_key"] = group_key
        seen[group_key] = merged
    return list(seen.values()), merge_notes


def _step_drug_interactions(backend: str, drugs: List[Dict[str, Any]], progress: Progress) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "drugbank_loaded": False, "matched": [], "interactions": [], "unmatched": []}
    progress.start("drug interactions")
    payload = {
        "drugs": [
            {
                "name": d["name"],
                "chembl_id": d.get("chembl_id"),
                "drugbank_id": d.get("drugbank_id"),
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
    progress.end("ok", f"{len(interactions)} interactions")
    return {
        "ok": True,
        "drugbank_loaded": bool(body.get("drugbank_loaded")),
        "matched": body.get("matched") or [],
        "interactions": interactions,
        "unmatched": body.get("unmatched") or [],
    }


def _step_target_overlap(backend: str, drugs: List[Dict[str, Any]], progress: Progress) -> Dict[str, Any]:
    if not drugs:
        return {"ok": True, "targets_by_drug": [], "overlaps": [], "unmatched": []}
    progress.start("target overlap")
    payload = {"drugs": [{"name": d["name"], "chembl_id": d.get("chembl_id")} for d in drugs]}
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
        "drugs": [{"name": d["name"], "chembl_id": d.get("chembl_id")} for d in drugs],
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


def _fetch_drug_trials(backend: str, chembl_id: str, limit: int) -> Tuple[str, Dict[str, Any]]:
    qs = urllib.parse.urlencode({"limit": str(limit)})
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
) -> Dict[str, Any]:
    with_chembl = [d for d in drugs if d.get("chembl_id")]
    skipped = [d["name"] for d in drugs if not d.get("chembl_id")]
    if not with_chembl:
        return {"ok": True, "by_drug": {}, "skipped_no_chembl_id": skipped}
    progress.start(f"drug trials ×{len(with_chembl)}")
    by_drug: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(with_chembl))) as pool:
        futures = [pool.submit(_fetch_drug_trials, backend, d["chembl_id"], limit) for d in with_chembl]
        for f in futures:
            chembl_id, result = f.result()
            by_drug[chembl_id] = result
    total = sum(len(v.get("trials") or []) for v in by_drug.values())
    progress.end("ok", f"{total} trials")
    return {"ok": True, "by_drug": by_drug, "skipped_no_chembl_id": skipped}


# --- Ollama synthesis (optional) -------------------------------------------

def _ollama_synthesize(
    endpoint: str,
    model: str,
    plan: Dict[str, Any],
    findings: Dict[str, Any],
    progress: Progress,
) -> Dict[str, Any]:
    progress.start("ollama synthesis")
    prompt = _build_synthesis_prompt(plan, findings)
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
        with urllib.request.urlopen(req, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    progress.end("failed", obj["error"])
                    return {"ok": False, "error": obj["error"], "text": "".join(chunks)}
                piece = obj.get("response")
                if isinstance(piece, str) and piece:
                    chunks.append(piece)
                    if not progress.quiet:
                        sys.stderr.write(piece)
                        sys.stderr.flush()
                if obj.get("done"):
                    break
        if not progress.quiet:
            sys.stderr.write("\n")
        progress.end("ok", f"{sum(len(c) for c in chunks)} chars")
        return {"ok": True, "text": "".join(chunks)}
    except urllib.error.URLError as e:
        progress.end("failed", str(e.reason))
        return {"ok": False, "error": f"could not reach Ollama at {url}: {e.reason}"}
    except TimeoutError:
        progress.end("failed", "timeout")
        return {"ok": False, "error": f"timeout contacting Ollama at {url}"}


def _build_synthesis_prompt(plan: Dict[str, Any], findings: Dict[str, Any]) -> str:
    header_lines = [
        "You are auditing a cancer treatment plan. Produce a clinical-style audit",
        "with sections for: (1) plan summary, (2) NCI PDQ alignment, (3) drug-drug",
        "interactions, (4) mechanism overlap, (5) FAERS signal vs. reported symptoms,",
        "(6) relevant trials, (7) open questions for the prescriber. Do not invent",
        "facts; cite only what appears in FINDINGS.",
        "",
        "PLAN:",
        f"  Cancer type: {plan.get('cancer_type_display') or plan.get('cancer_type')}",
        f"  Subtype: {plan.get('subtype_display') or plan.get('subtype')}",
        f"  Stage: {plan.get('stage') or '(unspecified)'}",
        f"  Stage detail: {plan.get('stage_detail') or '(none)'}",
        f"  Drugs: {', '.join(d['name'] for d in plan.get('drugs', [])) or '(none)'}",
        f"  Treatments: {', '.join(plan.get('treatments') or []) or '(none)'}",
        f"  Symptoms: {', '.join(s['text'] + ' (' + s['severity'] + ')' for s in plan.get('symptoms') or []) or '(none)'}",
        "",
        "FINDINGS (JSON):",
    ]
    return "\n".join(header_lines) + "\n" + json.dumps(findings, indent=2)


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

    if "synthesis" in result:
        synth = result["synthesis"]
        out.append("--- ai synthesis ---")
        if synth.get("ok"):
            out.append(synth.get("text") or "")
        else:
            out.append(f"FAILED: {synth.get('error')}")
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
    parser.add_argument("--with-ollama", action="store_true", help="Also stream a final AI synthesis from Ollama.")
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

    try:
        plan_raw = _load_plan(args.plan)
        plan = _validate_plan(plan_raw)
        _check_backend(args.backend)
        plan = _resolve_taxonomy(args.backend, plan, progress)
    except CLIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    steps: Dict[str, Any] = {}

    if "pdq" not in skip_set:
        steps["pdq"] = _step_pdq(args.backend, plan, progress)
    if "modality" not in skip_set:
        steps["modality_trials"] = _step_modality(args.backend, plan, args.modality_limit, progress)

    if "rxnorm" not in skip_set:
        rxnorm = _step_rxnorm(args.backend, plan["drugs"], progress)
    else:
        rxnorm = {"ok": True, "skipped_by_user": True, "deduped_drugs": list(plan["drugs"])}
    steps["rxnorm"] = rxnorm
    deduped = rxnorm.get("deduped_drugs") or list(plan["drugs"])

    if "interactions" not in skip_set:
        steps["drug_interactions"] = _step_drug_interactions(args.backend, deduped, progress)
    if "targets" not in skip_set:
        steps["target_overlap"] = _step_target_overlap(args.backend, deduped, progress)
    if "faers" not in skip_set:
        steps["adverse_events"] = _step_faers(args.backend, deduped, plan["symptoms"], progress)
    if "drug-trials" not in skip_set:
        steps["drug_trials"] = _step_drug_trials(args.backend, deduped, args.drug_trials_limit, progress)

    result: Dict[str, Any] = {"plan": plan, "steps": steps}

    if args.with_ollama:
        result["synthesis"] = _ollama_synthesize(
            args.ollama_endpoint,
            args.ollama_model,
            plan,
            steps,
            progress,
        )

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

    pdq = steps.get("pdq", {})
    pdq_ok = pdq.get("ok") and (pdq.get("skipped") or pdq.get("data"))
    modality = steps.get("modality_trials", {})
    any_trials = bool(modality.get("ok") and any(
        v.get("ok") and v.get("trials") for v in (modality.get("by_modality") or {}).values()
    ))
    drug_trials = steps.get("drug_trials", {})
    any_drug_trials = bool(drug_trials.get("ok") and any(
        v.get("ok") and v.get("trials") for v in (drug_trials.get("by_drug") or {}).values()
    ))
    return 0 if (pdq_ok and (any_trials or any_drug_trials or "modality" in skip_set or "drug-trials" in skip_set)) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
