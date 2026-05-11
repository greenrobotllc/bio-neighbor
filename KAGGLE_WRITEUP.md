# BioNeighbor Treatment Auditor

### A patient's "second opinion" that synthesizes six public medical databases into a citation-grounded PDF — running entirely on the patient's laptop, powered by Gemma 4.

**Track:** Health & Sciences

---

## The Sunday-night problem

A cancer diagnosis arrives faster than a person can process it. Within a few visits the patient has a stage, a subtype, three drugs they've never heard of, and a calendar of infusions. They want a second opinion. The honest second opinion looks like this: open seven tabs, read NCI PDQ, search ClinicalTrials.gov, cross-reference DDInter for drug interactions, check ChEMBL for mechanism overlap, look up OpenFDA FAERS to see what other patients reported, normalize names through RxNorm because the hospital wrote "Taxol" and the trial database says "paclitaxel" — then synthesize all of it into questions they can ask their oncologist on Monday.

Most patients can't do this. The ones who try usually stop halfway, exhausted. And pasting a treatment plan into a cloud chatbot is a privacy non-starter: this is the most sensitive data a person owns.

## What we built

**BioNeighbor Treatment Auditor** turns that Sunday-night research session into a 90-second audit on the patient's own machine. The patient enters cancer type, subtype, stage, drugs, treatments, and symptoms. A multi-pass pipeline pulls from six public medical databases, runs four deterministic safety lookups, then hands the structured findings to **Gemma 4 26B** running locally via Ollama. The output is a self-contained, paginated PDF with every NCT ID, every PDQ URL, and every data-source citation listed in a References section — enough detail that a clinician could reproduce the audit by hand.

**Everything runs locally.** The Ollama endpoint is hard-pinned to `127.0.0.1:11434`; the Flask backend to `127.0.0.1:5000`. There is no cloud API key, no telemetry, no fallback to a remote LLM. The only external network traffic is the one-time download of public medical datasets — the same fetches a researcher would make from PubMed.

## Why Gemma 4

Three properties of the Gemma 4 family map directly onto this problem:

1. **Frontier reasoning on consumer hardware.** Gemma 4 26B fits on a single Apple-silicon Mac with 64 GB unified memory (we develop on an M1) or a workstation with one RTX A5000-class GPU. We didn't have to trade reasoning quality for offline operation — a non-negotiable trade-off for medical synthesis.
2. **The family's range covers the deployment spectrum.** The same architecture and prompts work with Gemma 4's smaller siblings. A clinic with older hardware can run the same audit pipeline on a 4B variant; a research workstation can scale to 26B or 31B for tougher synthesis. We don't have to fork the application per device class.
3. **Open weights are load-bearing for the offline guarantee.** Closed-API models can't run on a HIPAA-firewalled hospital wing, on a plane between consultations, or in a country where uploading patient data to a US cloud is illegal. Gemma 4's open weights are the only reason this app exists.

## Architecture

The audit is three layers, each producing material that flows into the next:

**Layer 1 — Deterministic safety lookups (no LLM).** Before the model sees anything, four pure-Python passes run:
- **RxNorm dedupe** collapses brand-vs-generic duplicates (Taxol + paclitaxel → one ingredient row) so the audit doesn't double-count fan-out per drug.
- **DDInter pairwise interactions** flags Major / Moderate / Minor drug-drug interactions from a 236k-pair offline database (CC BY-NC-SA 4.0, ~13 MB).
- **ChEMBL mechanism overlap** surfaces when two drugs hit the same gene (e.g., anastrozole + letrozole both inhibit CYP19A1) — could be intentional combination therapy, could be redundant, worth raising.
- **OpenFDA FAERS** matches the patient's reported symptoms against the top reactions for each prescribed drug ("fatigue is the #1 reported reaction for tamoxifen — 386 reports of 5,613").

These render as factual callouts *above* the AI prose. The LLM cannot contradict them; it can only contextualize them.

**Layer 2 — Per-source mini-summaries (Gemma 4).** For each public dataset (NCI PDQ standard-of-care text, ClinicalTrials.gov modality trials by radiation/surgery/chemotherapy/targeted, per-drug trials via ChEMBL→NCT), Gemma 4 reads the raw records and writes a short summary scoped to the patient's plan. Each summary streams token-by-token to the macOS app — on consumer hardware a 26B-driven audit takes several minutes end-to-end, which is exactly why streaming matters: the patient watches the audit assemble itself, one cited source at a time, instead of staring at a spinner. This pattern (focused context per source, narrow prompt, streamed output) is the whole reason this works on a laptop: Gemma 4 never has to ingest the entire corpus at once.

**Layer 3 — Final synthesis pass (Gemma 4).** A second model call receives the deterministic findings, the per-source summaries, and the patient's plan, then produces a 350-550 word audit organized into seven sections — standard-of-care alignment, interaction flags, mechanism interpretation, symptoms vs adverse-event profiles, trial landscape, staging implications, and questions to ask the oncology team. The output is rendered to HTML, then to PDF via WeasyPrint, with the deterministic callouts, methodology notes, pipeline log, per-source summaries, and References section all stitched together. The macOS app and the cross-platform Python CLI hit the same `/treatment-auditor/report.pdf` endpoint — one source of truth for layout and copy.

## What we shipped (and what we deliberately didn't)

Honest scope notes for the judges:

- **Plain-text prompting.** Per-source and synthesis calls are NDJSON-streamed text-in/text-out against Ollama's `/api/generate`. No function calling, no structured-output mode, no JSON-schema coercion. The synthesis prompt is engineered tightly enough that we don't need them; the deterministic layer handles everything that *must* be machine-parseable.
- **Text-only inputs to the model.** PDQ HTML, trial records, and FAERS rows are compressed into text blocks by the backend before reaching Gemma. The model never sees raw PDFs or images. Multimodal inputs (prior pathology PDFs, imaging summaries) are on the roadmap — they fit Gemma 4's capabilities, but we wanted the v1 audit pipeline to be rock-solid first.
- **Streaming where it matters.** The macOS app streams every mini-summary so users watch the audit assemble itself; the CLI streams only the final synthesis (mini-summaries are buffered for clean stdout JSON).

## Engineering rigor

A few choices worth flagging:

- **Atomic data reloads.** The DDInter loader pulls eight ATC-class CSVs (~236k pairs). The earlier implementation wiped the live table first, then streamed inserts — if the loader crashed mid-load, the audit would silently render *"no interactions found"* instead of *"data unavailable."* We rebuilt it to stage every row into `drug_interactions_tmp`, then swap inside a single `DELETE` + `INSERT FROM SELECT` transaction. Readers see the prior data right up until commit and the new data the instant after. Never zero, never half.
- **Stage-hint scoping.** ClinicalTrials.gov v2's `query.term` is a soft bias, not a filter — but adding `"Stage IV"` to a surgery search zeros the result for advanced-stage patients, implying *"no surgical evidence"* when the real story is *"surgery isn't a primary modality at this stage."* We restricted the hint to chemotherapy and targeted-therapy searches; the synthesis prompt frames staging implications separately.
- **PDF integrity.** The macOS client now validates `Content-Type: application/pdf` and the `%PDF-` magic before writing — so a misconfigured proxy or backend regression can't produce a "PDF" that opens to gibberish.
- **CodeQL-clean error handling.** Static analysis flagged exception-message echoes as info-exposure sinks. Validation layer was rebuilt with literal error strings only; no client-supplied content flows back into responses.

## Impact

This is a research tool, not medical advice — and "research tool" undersells what it does for a patient the night before chemo starts. The audit runs in the time it takes to make a pot of coffee on an Apple-silicon laptop, and produces a printable, citation-rich PDF the patient can mark up on the train and hand to their oncologist as *"these are the questions I want to ask."* That conversation — informed, specific, cited — is qualitatively different from *"I read something on Reddit."*

Because everything runs on Gemma 4, the audit works in a rural cancer center with bad Wi-Fi, in a hospital wing where the network is firewalled for HIPAA, on a patient's plane ride between consultations, and in jurisdictions where uploading patient data to a US cloud is illegal.

## What's next

- **Multimodal intake** — let patients drop prior pathology PDFs and imaging summaries directly into the audit, leveraging Gemma 4's vision capabilities.
- **Tumor-mutation matching** — integrate TCGA + OncoKB so the trial fan-out can match on genomic profile, not just histology.
- **Multilingual synthesis** — Gemma 4's multilingual reach lets us render the same audit in Spanish, Portuguese, Mandarin natively, without a separate translation step.
- **Mobile** — package an E4B-class build for clinician handheld use during rounds.

---

**Project Links** (attached on the Kaggle Writeup page): YouTube demo, public GitHub repo, example audit PDF (`example_reports/treatment-audit-her2-20260507-1433.pdf`), `setup.sh` for one-command local install.

*BioNeighbor is MIT-licensed; medical datasets carry their own licenses (notably DDInter is CC BY-NC-SA 4.0 — non-commercial use only). Research tool. Not medical advice.*
