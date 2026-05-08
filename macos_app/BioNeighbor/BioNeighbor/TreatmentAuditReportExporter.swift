//
//  TreatmentAuditReportExporter.swift
//  BioNeighbor
//
//  Renders a completed Treatment Auditor run (issue #58) as a printable PDF.
//
//  The report captures everything a reader needs to re-run the audit by hand:
//    - all user inputs (cancer type/subtype/markers, stage, drugs, treatments,
//      symptoms),
//    - the multi-pass methodology (PDQ + ClinicalTrials.gov modality and
//      per-drug searches → per-source mini-summaries → final synthesis),
//    - the live audit step log,
//    - every per-source mini-summary,
//    - the final synthesis,
//    - a References section listing each NCT ID and the PDQ URL,
//    - generation timestamp and a link back to the bio-neighbor repo.
//
//  Implementation: builds an HTML document, loads it into a temporary
//  WKWebView, and asks WebKit for paginated PDF data via createPDF.
//

import AppKit
import Foundation
import WebKit

// MARK: - Snapshot the auditor view passes in

/// One per-source mini-summary as captured during the audit run.
struct AuditSourceSummary: Hashable {
    let label: String
    let summary: String
}

/// Frozen snapshot of a finished audit. Held by `TreatmentAuditorView` so the
/// "Save as PDF…" button can render exactly what the user just saw, even if
/// they edit the form afterwards.
///
/// `plan` carries the deterministic findings the PDF renders alongside the
/// inputs (drug interactions, target overlap, FAERS matches). `mergeNotes`
/// is captured separately because the merge happens *before* `plan.drugs` is
/// populated — by the time the plan exists, the original brand/generic
/// duplicates have already been collapsed and we need the audit history to
/// recover what was merged.
struct CompletedAuditSnapshot {
    let plan: TreatmentAuditPlan
    let sourceSummaries: [AuditSourceSummary]
    let finalAudit: String
    let steps: [AuditStep]
    let generatedAt: Date
    /// Brand→generic merges flagged by the RxNorm dedupe step (issue #55).
    /// Empty when no inputs collapsed.
    var mergeNotes: [DrugMergeNote] = []
    /// FAERS per-drug top events captured for the report (issue #46).
    /// Stored on the snapshot rather than the plan because the LLM prompt
    /// only needs the symptom→reaction matches; the full per-drug top
    /// list is for the human reader of the PDF.
    var faersPanels: [FAERSDrugPanel] = []
}

// MARK: - Public exporter

@MainActor
enum TreatmentAuditReportExporter {

    static let repoURL = "https://github.com/greenrobotllc/bio-neighbor"

    /// Render the supplied snapshot as PDF and write it to `outputURL`.
    /// Throws on WebKit load/print failures.
    static func exportPDF(snapshot: CompletedAuditSnapshot, to outputURL: URL) async throws {
        let html = buildHTML(snapshot: snapshot)
        try await renderHTMLToPDF(html: html, outputURL: outputURL)
    }

    /// Suggested filename for NSSavePanel — `treatment-audit-<slug>-<stamp>.pdf`.
    static func defaultFilename(for snapshot: CompletedAuditSnapshot) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmm"
        let stamp = formatter.string(from: snapshot.generatedAt)
        let raw = snapshot.plan.subtypeName ?? snapshot.plan.cancerTypeName
        let slug = sanitizeForFilename(raw)
        let base = slug.isEmpty ? "audit" : slug
        return "treatment-audit-\(base)-\(stamp).pdf"
    }

    // MARK: - PDF rendering

    /// Loads `html` into an off-screen WKWebView and prints it through
    /// `NSPrintOperation` with `.save` disposition, producing a paginated
    /// PDF on disk. We deliberately do NOT use `WKWebView.createPDF` here:
    /// that API snapshots the entire rendered document into a single
    /// monster page (the report would land as one ~97-inch-tall page that
    /// preview/print-engines just squish), whereas the print pipeline
    /// honors paper size + margins and paginates content normally.
    ///
    /// Two non-obvious bits make this work reliably:
    ///   - The WebView lives inside an off-screen NSWindow that is actually
    ///     `orderFront`-ed (positioned far off-screen so it stays invisible).
    ///     A windowless or hidden WKWebView never runs full layout, and the
    ///     print pipeline crashes with WKPrintingView's "frame not
    ///     initialized before knowsPageRange:" assertion.
    ///   - We explicitly set `op.view?.frame` to the page size before
    ///     `op.run()`. WebKit creates a private WKPrintingView for the job
    ///     whose frame is otherwise zero at the moment NSPrintOperation
    ///     queries `knowsPageRange:`, which trips the same assertion.
    private static func renderHTMLToPDF(html: String, outputURL: URL) async throws {
        // 8.5 × 11 inch in PostScript points (1 in = 72 pt).
        let pageSize = NSSize(width: 8.5 * 72, height: 11 * 72)
        let frame = NSRect(origin: .zero, size: pageSize)

        let webView = WKWebView(frame: frame)
        let coordinator = LoadCoordinator()
        webView.navigationDelegate = coordinator

        // Off-screen carrier window — positioned at -20000,-20000 so it is
        // never visible to the user but is a real, ordered-front window so
        // layout runs. `isReleasedWhenClosed = false` keeps lifetime tied
        // to this scope rather than AppKit's auto-release on close.
        let window = NSWindow(
            contentRect: NSRect(x: -20_000, y: -20_000,
                                width: pageSize.width, height: pageSize.height),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.orderFront(nil)

        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            coordinator.continuation = cont
            webView.loadHTMLString(html, baseURL: nil)
        }

        // didFinish fires before late-stage layout (web fonts, reflow) settles.
        // A short delay before printing gives WebKit time to finalize layout
        // so we don't snapshot mid-paint.
        try await Task.sleep(nanoseconds: 300_000_000)
        webView.layoutSubtreeIfNeeded()

        let info = NSPrintInfo()
        info.paperSize = pageSize
        info.topMargin = 0.6 * 72
        info.bottomMargin = 0.6 * 72
        info.leftMargin = 0.6 * 72
        info.rightMargin = 0.6 * 72
        info.horizontalPagination = .automatic
        info.verticalPagination = .automatic
        info.isHorizontallyCentered = false
        info.isVerticallyCentered = false
        info.orientation = .portrait
        info.jobDisposition = .save
        info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = outputURL as NSURL

        let op = webView.printOperation(with: info)
        op.showsPrintPanel = false
        op.showsProgressPanel = false
        // Critical: explicitly size the print view *before* the operation
        // starts so WKPrintingView's `knowsPageRange:` doesn't see a zero
        // frame and hit its "frame was not initialized properly" assertion.
        op.view?.frame = frame

        // Run via the async sheet API instead of the synchronous `run()`.
        // `run()` blocks the main thread end-to-end, freezing the entire
        // app while WebKit paginates the document. `runModal(for:…)` kicks
        // the job off as a (visually invisible — both panels are off)
        // window-attached operation that completes via the supplied
        // selector, so the main runloop stays free to redraw the UI and
        // animate the "Rendering report…" indicator.
        //
        // The delegate is held in a local strong reference for the whole
        // function — NSPrintOperation does NOT retain its modal delegate
        // (per the modal-delegate pattern), and dropping it before the
        // callback fires would dangle.
        var target: PrintCompletionTarget?
        let success: Bool = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            let t = PrintCompletionTarget { ok in cont.resume(returning: ok) }
            target = t
            op.runModal(
                for: window,
                delegate: t,
                didRun: #selector(PrintCompletionTarget.printOperationDidRun(_:success:contextInfo:)),
                contextInfo: nil
            )
        }
        _ = target  // explicit live-use; keeps the delegate alive past `await`

        // Tear down the off-screen window cleanly.
        window.orderOut(nil)
        window.contentView = nil

        guard success else {
            throw NSError(
                domain: "TreatmentAuditReportExporter",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Print operation failed."]
            )
        }
    }

    // MARK: - HTML builder

    private static func buildHTML(snapshot: CompletedAuditSnapshot) -> String {
        let timestamp = isoTimestamp(snapshot.generatedAt)

        var body = ""
        body += headerSection(timestamp: timestamp)
        body += disclaimerSection()
        body += inputsSection(plan: snapshot.plan)
        body += deterministicFindingsSection(snapshot: snapshot)
        body += methodologySection(snapshot: snapshot)
        body += pipelineLogSection(steps: snapshot.steps)
        body += sourceSummariesSection(summaries: snapshot.sourceSummaries)
        body += finalAuditSection(text: snapshot.finalAudit)
        body += referencesSection(plan: snapshot.plan)
        body += footerSection(timestamp: timestamp)

        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Treatment Auditor Report</title>
        <style>\(stylesheet)</style>
        </head>
        <body>
        \(body)
        </body>
        </html>
        """
    }

    // MARK: HTML sections

    private static func headerSection(timestamp: String) -> String {
        """
        <header class="report-header">
          <h1>Bio-Neighbor Treatment Auditor Report</h1>
          <div class="muted">Generated \(escape(timestamp))</div>
          <div class="muted">Source: <a href="\(repoURL)">\(repoURL)</a></div>
        </header>
        """
    }

    private static func disclaimerSection() -> String {
        """
        <section class="disclaimer">
          <strong>Research tool only — not medical advice.</strong>
          This report compiles publicly available data from NCI PDQ and
          ClinicalTrials.gov plus on-device LLM summaries. Discuss any
          treatment-plan questions with your oncology team.
        </section>
        """
    }

    private static func inputsSection(plan: TreatmentAuditPlan) -> String {
        var rows: [String] = []
        rows.append(row(label: "Cancer type", value: plan.cancerTypeName))
        if let subtype = plan.subtypeName, !subtype.isEmpty {
            rows.append(row(label: "Subtype", value: subtype))
        }
        if let markers = plan.subtypeMarkers, !markers.isEmpty {
            rows.append(row(label: "Markers", value: markers.joined(separator: ", ")))
        }
        rows.append(row(label: "Stage", value: plan.stage ?? "Unspecified"))
        if let detail = plan.stageDetail, !detail.isEmpty {
            rows.append(row(label: "Stage detail", value: detail))
        }

        if plan.drugs.isEmpty {
            rows.append(row(label: "Prescribed drugs", value: "(none)"))
        } else {
            let drugItems = plan.drugs.map { drug -> String in
                let chembl = drug.chemblId.map { " (\(escape($0)))" } ?? ""
                return "<li>\(escape(drug.name))\(chembl)</li>"
            }.joined()
            rows.append(row(label: "Prescribed drugs", rawValue: "<ul class=\"plain\">\(drugItems)</ul>"))
        }

        if plan.treatments.isEmpty {
            rows.append(row(label: "Scheduled treatments", value: "(none)"))
        } else {
            let items = plan.treatments.map { "<li>\(escape($0))</li>" }.joined()
            rows.append(row(label: "Scheduled treatments", rawValue: "<ul class=\"plain\">\(items)</ul>"))
        }

        if plan.symptoms.isEmpty {
            rows.append(row(label: "Symptoms / side effects", value: "(none)"))
        } else {
            let items = plan.symptoms.map { sym -> String in
                if let severity = sym.severity, !severity.isEmpty {
                    return "<li>\(escape(sym.text)) <span class=\"chip\">\(escape(severity))</span></li>"
                }
                return "<li>\(escape(sym.text))</li>"
            }.joined()
            rows.append(row(label: "Symptoms / side effects", rawValue: "<ul class=\"plain\">\(items)</ul>"))
        }

        return """
        <section class="section">
          <h2>1. Inputs</h2>
          <table class="kv">\(rows.joined())</table>
        </section>
        """
    }

    /// Deterministic-findings section — surfaces the four
    /// non-LLM-inferred audit outputs so the PDF mirrors the on-screen
    /// callouts:
    ///   - Brand→generic merges (RxNorm, issue #55)
    ///   - Pairwise drug-drug interactions (DrugBank, issue #47)
    ///   - Mechanism/target overlap (ChEMBL mechanisms, issue #53)
    ///   - FAERS top reactions + symptom matches (OpenFDA, issue #46)
    ///
    /// Each block is rendered only when there's data to show, so an audit
    /// that produced no findings keeps the PDF compact.
    private static func deterministicFindingsSection(snapshot: CompletedAuditSnapshot) -> String {
        let plan = snapshot.plan

        let merges = mergesBlock(snapshot.mergeNotes)
        let interactions = interactionsBlock(plan)
        let overlaps = overlapsBlock(plan)
        let faers = faersBlock(plan: plan, panels: snapshot.faersPanels)

        let blocks = [merges, interactions, overlaps, faers].filter { !$0.isEmpty }
        if blocks.isEmpty {
            // No deterministic findings — drop the whole section rather
            // than render an empty heading.
            return ""
        }

        return """
        <section class="section">
          <h2>2. Deterministic findings</h2>
          <p class="muted">
            Factual lookups produced before the LLM passes — sourced from
            RxNorm, DrugBank, ChEMBL, and openFDA respectively. The audit
            synthesis (section 6) is instructed to repeat these verbatim
            rather than infer new ones.
          </p>
          \(blocks.joined())
        </section>
        """
    }

    private static func mergesBlock(_ notes: [DrugMergeNote]) -> String {
        guard !notes.isEmpty else { return "" }
        let rows = notes.map { note -> String in
            let originals = note.originalNames.map { escape($0) }.joined(separator: " + ")
            return "<li>\(originals) → <strong>\(escape(note.ingredientName))</strong></li>"
        }.joined()
        return """
        <h3>Brand → generic dedupe (RxNorm)</h3>
        <p>The following input pairs collapsed onto a single ingredient
           via RxNorm normalization. Per-drug fetches downstream used the
           merged entry, so trial / interaction / overlap / FAERS results
           are not duplicated for the same active ingredient:</p>
        <ul>\(rows)</ul>
        """
    }

    private static func interactionsBlock(_ plan: TreatmentAuditPlan) -> String {
        // We render a block in two cases:
        //  1. There are interactions to list.
        //  2. Interactions data was unavailable (DrugBank XML not loaded)
        //     — that's a meaningfully different statement from "none
        //     found", and the report should say so explicitly.
        if plan.drugInteractions.isEmpty && plan.drugInteractionDataAvailable {
            return ""
        }

        if !plan.drugInteractionDataAvailable {
            return """
            <h3>Pairwise drug-drug interactions (DrugBank)</h3>
            <p class="muted">
              The DrugBank XML hasn't been loaded into the local
              <code>drug_interactions</code> table on this install, so
              pairwise drug-drug interactions could not be checked. This
              is not the same as "no interactions found" — the audit
              cannot speak to interactions at all in this state.
              Run <code>python backend/load_drugbank_interactions.py</code>
              after dropping the DrugBank XML at
              <code>data/drugbank_cache/drugbank.xml</code> (free academic
              registration at <a href="https://go.drugbank.com">go.drugbank.com</a>)
              to enable this check.
            </p>
            """
        }

        let rows = plan.drugInteractions.map { row -> String in
            let sev = (row.severity?.isEmpty == false) ? row.severity! : "unknown"
            let desc = row.description ?? ""
            let cls = severityCSSClass(row.severity)
            return """
            <tr>
              <td>\(escape(row.drugA)) ↔ \(escape(row.drugB))</td>
              <td><span class="\(cls)">\(escape(sev.uppercased()))</span></td>
              <td>\(escape(desc))</td>
            </tr>
            """
        }.joined()

        return """
        <h3>Pairwise drug-drug interactions (DrugBank)</h3>
        <p>Source: DrugBank pairwise <code>drug-interactions</code>
           records. Severity is heuristic from the description text —
           confirm with the prescribing clinician.</p>
        <table class="data">
          <thead><tr><th>Pair</th><th>Severity</th><th>Description</th></tr></thead>
          <tbody>\(rows)</tbody>
        </table>
        """
    }

    private static func overlapsBlock(_ plan: TreatmentAuditPlan) -> String {
        guard !plan.targetOverlaps.isEmpty else { return "" }
        let rows = plan.targetOverlaps.map { row -> String in
            let target = row.geneSymbol ?? row.proteinName ?? "shared target"
            let actionA = row.actionTypeA ?? "—"
            let actionB = row.actionTypeB ?? "—"
            return """
            <tr>
              <td>\(escape(row.drugA)) ↔ \(escape(row.drugB))</td>
              <td><code>\(escape(target))</code></td>
              <td>\(escape(actionA.lowercased()))</td>
              <td>\(escape(actionB.lowercased()))</td>
            </tr>
            """
        }.joined()
        return """
        <h3>Mechanism / target overlap (ChEMBL)</h3>
        <p>Source: ChEMBL <code>mechanism</code> +
           <code>target</code> resources. Overlap on its own does not
           imply a problem — combination therapy is often intentional —
           but it's worth raising with the prescriber.</p>
        <table class="data">
          <thead>
            <tr>
              <th>Pair</th>
              <th>Shared target</th>
              <th>Drug A action</th>
              <th>Drug B action</th>
            </tr>
          </thead>
          <tbody>\(rows)</tbody>
        </table>
        """
    }

    private static func faersBlock(plan: TreatmentAuditPlan, panels: [FAERSDrugPanel]) -> String {
        let hasMatches = !plan.faersSymptomMatches.isEmpty
        let hasPanels = !panels.isEmpty
        if !hasMatches && !hasPanels { return "" }

        var pieces: [String] = []
        pieces.append("""
        <h3>OpenFDA FAERS post-market reporting</h3>
        <p>Source: openFDA <code>/drug/event.json</code>. Reports are
           voluntary and do not establish causation; counts reflect what
           has been reported, not actual incidence.</p>
        """)

        if hasMatches {
            let rows = plan.faersSymptomMatches.map { m -> String in
                let rank = m.rankInTop.map { "#\($0)" } ?? "—"
                return """
                <tr>
                  <td>\(escape(m.drugName))</td>
                  <td>\(escape(m.symptom))</td>
                  <td>\(escape(m.matchedTerm))</td>
                  <td>\(rank)</td>
                  <td>\(m.count.formatted())</td>
                  <td>\(m.totalReports.formatted())</td>
                </tr>
                """
            }.joined()
            pieces.append("""
            <h4>Symptom → reaction matches</h4>
            <table class="data">
              <thead>
                <tr>
                  <th>Drug</th><th>Symptom</th><th>Matched FAERS term</th>
                  <th>Rank in top reactions</th><th>Reports</th><th>Total reports for drug</th>
                </tr>
              </thead>
              <tbody>\(rows)</tbody>
            </table>
            """)
        }

        if hasPanels {
            let panelHTML = panels.map { panel -> String in
                let evRows = panel.topEvents.prefix(10).map { ev in
                    "<tr><td>\(escape(ev.term))</td><td>\(ev.count.formatted())</td></tr>"
                }.joined()
                let bodyHTML: String
                if evRows.isEmpty {
                    bodyHTML = "<p class=\"muted\"><em>No reports returned for this drug.</em></p>"
                } else {
                    bodyHTML = """
                    <table class="data">
                      <thead><tr><th>Reaction term</th><th>Reports</th></tr></thead>
                      <tbody>\(evRows)</tbody>
                    </table>
                    """
                }
                return """
                <h4>\(escape(panel.drugName)) — \(panel.totalReports.formatted()) total reports</h4>
                \(bodyHTML)
                """
            }.joined()
            pieces.append("<h4>Top reported reactions per drug</h4>\(panelHTML)")
        }

        return pieces.joined()
    }

    private static func severityCSSClass(_ severity: String?) -> String {
        switch (severity ?? "").lowercased() {
        case "severe": return "sev-severe"
        case "moderate": return "sev-moderate"
        case "minor": return "sev-minor"
        default: return "sev-unknown"
        }
    }

    /// Methodology section — the heart of issue #58. Documents every step
    /// taken so a reader can reproduce the audit by hand.
    private static func methodologySection(snapshot: CompletedAuditSnapshot) -> String {
        let plan = snapshot.plan
        let summaryCount = snapshot.sourceSummaries.count

        // PDQ block.
        var pdqBlock: String
        if let pdq = plan.pdqSummary {
            let stageLine: String
            if let stage = pdq.stage, !stage.isEmpty {
                stageLine = "Filtered for stage: <code>\(escape(stage))</code>"
            } else {
                stageLine = "No stage filter applied."
            }
            let detailLine: String
            if let detail = pdq.stageDetail, !detail.isEmpty {
                detailLine = " &nbsp;Stage-detail tokens scored against headings + body: <code>\(escape(detail))</code>."
            } else {
                detailLine = ""
            }
            let sectionTitles = pdq.sections
                .map { "<li><code>\(escape($0.title))</code> (h\($0.level))</li>" }
                .joined()
            pdqBlock = """
            <h3>NCI PDQ — Health Professional</h3>
            <p>URL fetched: <a href="\(escape(pdq.sourceURL))">\(escape(pdq.sourceURL))</a></p>
            <p>\(stageLine)\(detailLine)</p>
            <p>The page is parsed for <code>h2/h3/h4 + p/li</code>; sections are scored
               against (stage keywords, marker keywords, stage-detail tokens) with
               always-include for "stage information", "treatment option overview",
               "surgical treatment", "radiation therapy". Top-N kept, capped at
               6&nbsp;sections / 6,000&nbsp;chars total. Sections retained for this run:</p>
            <ul>\(sectionTitles)</ul>
            """
        } else {
            pdqBlock = """
            <h3>NCI PDQ — Health Professional</h3>
            <p>No PDQ summary available for this cancer type (hematologic / rare
               cancers are intentionally unmapped). Skipped.</p>
            """
        }

        // Modality search block.
        let modalityRows = plan.modalityTrials.map { entry -> String in
            let term = modalityInterventionTerm(entry.modality)
            let trialCount = entry.trials.count
            return """
            <tr>
              <td><code>\(escape(entry.modality))</code></td>
              <td><code>query.intr=\(escape(term))</code></td>
              <td>\(trialCount) trial\(trialCount == 1 ? "" : "s") returned</td>
            </tr>
            """
        }.joined()

        let conditionTerm = plan.subtypeName ?? plan.cancerTypeName
        let modalityBlock = """
        <h3>ClinicalTrials.gov — modality search</h3>
        <p>For each of the four modalities (radiation, surgery, chemotherapy,
           targeted), a parallel CT.gov v2 query is run via <code>GET /studies</code>
           with these parameters:</p>
        <ul>
          <li><code>query.cond</code> = subtype's first ChEMBL indication term if
              present, else the subtype name (this run: <code>\(escape(conditionTerm))</code>;
              the backend resolves the exact term server-side).</li>
          <li><code>query.intr</code> = modality intervention term (see table below).</li>
          <li><code>filter.overallStatus</code> = <code>COMPLETED|TERMINATED|ACTIVE_NOT_RECRUITING</code>
              — completed trials with reportable outcomes are preferred over
              actively-recruiting trials.</li>
          <li><code>pageSize</code> = 100, up to 3 pages, hard-capped at 300 raw
              records before sort.</li>
          <li>Sort: trials with multi-arm reported numeric outcomes first
              (apples-to-apples comparisons), then any-results, then more arms,
              with NCT-ID as a stable tiebreak.</li>
          <li>No date-range filter is applied; ordering does the prioritization.</li>
          <li>Up to 8 trials per modality are returned to the audit pass.</li>
        </ul>
        <table class="data">
          <thead><tr><th>Modality</th><th>CT.gov intervention term</th><th>Result</th></tr></thead>
          <tbody>\(modalityRows)</tbody>
        </table>
        """

        // Per-drug block.
        let drugRows = plan.drugTrials.map { entry -> String in
            let chembl = entry.chemblId ?? "—"
            let trialCount = entry.trials.count
            let detail: String
            if entry.chemblId == nil {
                detail = "No ChEMBL ID — trial fetch skipped."
            } else if trialCount == 0 {
                detail = "No trials returned."
            } else {
                detail = "\(trialCount) trial\(trialCount == 1 ? "" : "s") returned"
            }
            return """
            <tr>
              <td>\(escape(entry.drugName))</td>
              <td><code>\(escape(chembl))</code></td>
              <td>\(escape(detail))</td>
            </tr>
            """
        }.joined()

        let drugBlock = """
        <h3>ClinicalTrials.gov — per-drug trials</h3>
        <p>For each prescribed drug with a ChEMBL ID, NCT IDs are pulled from
           ChEMBL's <code>drug_indication</code> records, then each trial is
           fetched from CT.gov v2 (<code>GET /studies/&lt;NCT&gt;</code>) in
           parallel (max 5 concurrent). The same multi-arm-results-first sort
           is applied. Up to 10 trials per drug are surfaced.</p>
        <table class="data">
          <thead><tr><th>Drug</th><th>ChEMBL ID</th><th>Result</th></tr></thead>
          <tbody>\(drugRows.isEmpty ? "<tr><td colspan=\"3\"><em>No drugs supplied.</em></td></tr>" : drugRows)</tbody>
        </table>
        """

        // Multi-pass overview.
        let overview = """
        <h3>Multi-pass synthesis</h3>
        <p>The audit is intentionally split into many small LLM calls instead
           of one giant prompt — each source is summarized in isolation so a
           large source can't drown the others out, and the final synthesis
           reasons over the digests rather than the raw data:</p>
        <ol>
          <li><strong>Drug normalization.</strong> Each prescribed drug is
              resolved to an RxNorm ingredient RXCUI; brand-vs-generic
              duplicates are collapsed before any downstream fetch (issue #55).
              See section&nbsp;2 for the merges flagged for this run.</li>
          <li><strong>Deterministic safety lookups.</strong> Pairwise
              DrugBank drug-drug interactions (issue&nbsp;#47), ChEMBL
              mechanism-of-action target overlap among prescribed drugs
              (issue&nbsp;#53), and openFDA FAERS top reactions plus
              symptom→reaction matching (issue&nbsp;#46). All factual,
              non-LLM-inferred — surfaced in section&nbsp;2 and fed
              verbatim to the synthesis prompt as labelled "do-not-invent"
              context.</li>
          <li><strong>Source fetch.</strong> PDQ summary (1 call), modality
              trials (4 parallel CT.gov queries), per-drug trials
              (\(plan.drugTrials.count) parallel CT.gov queries).</li>
          <li><strong>Per-source mini-summaries.</strong> Each non-empty source
              is run through Ollama with the patient plan as context, producing
              a 120–180 word digest pointed at this patient's subtype/stage.
              \(summaryCount) mini-summar\(summaryCount == 1 ? "y" : "ies")
              produced for this run.</li>
          <li><strong>Final synthesis.</strong> A single Ollama call combines
              the patient plan (now including the deterministic findings
              from step&nbsp;2) + every mini-summary into the 350–550 word
              audit shown below, with explicit NCT-ID citations and a
              "Further reading" block. The raw source data is not in the
              synthesis prompt — the model only sees the mini-summaries it
              produced earlier and the deterministic-finding rows.</li>
        </ol>
        <p>This pipeline is fully reproducible by hand: pull the same PDQ page,
           run the same CT.gov queries listed above, query the same
           RxNorm / DrugBank / ChEMBL / openFDA endpoints with the same
           inputs, then paste each source into an LLM with the patient
           plan and ask for the same digests.</p>
        """

        return """
        <section class="section">
          <h2>3. Methodology &amp; data sources</h2>
          \(overview)
          \(pdqBlock)
          \(modalityBlock)
          \(drugBlock)
        </section>
        """
    }

    private static func pipelineLogSection(steps: [AuditStep]) -> String {
        guard !steps.isEmpty else { return "" }
        let rows = steps.map { step -> String in
            let (cssClass, label, detail) = stepRendering(step.state)
            let detailCell = detail.map { "<td class=\"muted\">\(escape($0))</td>" } ?? "<td></td>"
            return """
            <tr>
              <td class="\(cssClass)">\(escape(label))</td>
              <td>\(escape(step.label))</td>
              \(detailCell)
            </tr>
            """
        }.joined()
        return """
        <section class="section">
          <h2>4. Audit pipeline log</h2>
          <p class="muted">Live trace of fetches and LLM passes for this run.</p>
          <table class="data">
            <thead><tr><th>State</th><th>Step</th><th>Detail</th></tr></thead>
            <tbody>\(rows)</tbody>
          </table>
        </section>
        """
    }

    private static func sourceSummariesSection(summaries: [AuditSourceSummary]) -> String {
        guard !summaries.isEmpty else {
            return """
            <section class="section">
              <h2>5. Per-source summaries</h2>
              <p class="muted"><em>No per-source summaries were produced for this run.</em></p>
            </section>
            """
        }
        let blocks = summaries.map { entry -> String in
            """
            <div class="summary-block">
              <div class="label">\(escape(entry.label))</div>
              <div class="prose">\(paragraphs(from: entry.summary))</div>
            </div>
            """
        }.joined()
        return """
        <section class="section">
          <h2>5. Per-source summaries</h2>
          \(blocks)
        </section>
        """
    }

    private static func finalAuditSection(text: String) -> String {
        let body = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "<p class=\"muted\"><em>The final synthesis was empty for this run.</em></p>"
            : "<div class=\"prose\">\(paragraphs(from: text))</div>"
        return """
        <section class="section synthesis">
          <h2>6. Final audit</h2>
          \(body)
        </section>
        """
    }

    private static func referencesSection(plan: TreatmentAuditPlan) -> String {
        var entries: [String] = []

        if let pdq = plan.pdqSummary {
            entries.append("""
            <li><strong>NCI PDQ — \(escape(pdq.slug.capitalized)) (Health Professional):</strong>
                <a href="\(escape(pdq.sourceURL))">\(escape(pdq.sourceURL))</a></li>
            """)
        }

        // Deduplicate NCT IDs across modality + per-drug trials. Same NCT can
        // legitimately appear in both lists when a drug-linked trial also
        // matches the modality search; we list it once.
        var seen = Set<String>()
        var nctRows: [String] = []
        for entry in plan.modalityTrials {
            for trial in entry.trials where seen.insert(trial.nctId).inserted {
                nctRows.append(referenceLI(for: trial, context: "\(entry.modality.capitalized) trial"))
            }
        }
        for entry in plan.drugTrials {
            for trial in entry.trials where seen.insert(trial.nctId).inserted {
                nctRows.append(referenceLI(for: trial, context: "\(entry.drugName) trial"))
            }
        }
        if !nctRows.isEmpty {
            entries.append("""
            <li><strong>ClinicalTrials.gov studies cited / surfaced (\(nctRows.count)):</strong>
              <ul class="references">\(nctRows.joined())</ul>
            </li>
            """)
        }

        // Deterministic-finding sources — only listed when the audit
        // actually used them, so an audit with no interactions / overlap /
        // FAERS doesn't carry stale references.
        if !plan.drugInteractions.isEmpty {
            entries.append("""
            <li><strong>DrugBank drug-drug interactions:</strong>
                <a href="https://go.drugbank.com">https://go.drugbank.com</a>
                (pairwise <code>drug-interactions</code> records).</li>
            """)
        }
        if !plan.targetOverlaps.isEmpty {
            entries.append("""
            <li><strong>ChEMBL mechanism / target data:</strong>
                <a href="https://www.ebi.ac.uk/chembl/">https://www.ebi.ac.uk/chembl/</a>
                (<code>mechanism</code> + <code>target</code> resources).</li>
            """)
        }
        if !plan.faersSymptomMatches.isEmpty {
            entries.append("""
            <li><strong>OpenFDA FAERS adverse events:</strong>
                <a href="https://open.fda.gov/apis/drug/event/">https://open.fda.gov/apis/drug/event/</a></li>
            """)
        }

        entries.append("""
        <li><strong>RxNorm (drug name normalization):</strong>
            <a href="https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html">https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html</a></li>
        """)

        entries.append("""
        <li><strong>Bio-Neighbor source &amp; methodology:</strong>
            <a href="\(repoURL)">\(repoURL)</a></li>
        """)

        return """
        <section class="section">
          <h2>7. References</h2>
          <ul class="plain">\(entries.joined())</ul>
        </section>
        """
    }

    private static func footerSection(timestamp: String) -> String {
        """
        <footer class="footer">
          <p>Generated by Bio-Neighbor Treatment Auditor on \(escape(timestamp)).</p>
          <p>Repository: <a href="\(repoURL)">\(repoURL)</a></p>
          <p>Research tool only. Not medical advice. Discuss any plan changes with your oncology team.</p>
        </footer>
        """
    }

    // MARK: HTML helpers

    private static func referenceLI(for trial: ClinicalTrial, context: String) -> String {
        let url = "https://clinicaltrials.gov/study/\(trial.nctId)"
        let title = trial.title.map { " — \(escape($0))" } ?? ""
        return """
        <li><code>\(escape(trial.nctId))</code><span class="muted"> (\(escape(context)))</span>:
            <a href="\(escape(url))">\(escape(url))</a>\(title)</li>
        """
    }

    private static func row(label: String, value: String) -> String {
        "<tr><th>\(escape(label))</th><td>\(escape(value))</td></tr>"
    }

    private static func row(label: String, rawValue: String) -> String {
        "<tr><th>\(escape(label))</th><td>\(rawValue)</td></tr>"
    }

    private static func paragraphs(from text: String) -> String {
        // Split on blank lines so the LLM's paragraph breaks survive; HTML-
        // escape each chunk so markdown-ish stars / NCT IDs render literally
        // and not as broken markup.
        let chunks = text
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if chunks.isEmpty { return "" }
        return chunks.map { "<p>\(escape($0).replacingOccurrences(of: "\n", with: "<br>"))</p>" }.joined()
    }

    private static func escape(_ s: String) -> String {
        var out = s
        out = out.replacingOccurrences(of: "&", with: "&amp;")
        out = out.replacingOccurrences(of: "<", with: "&lt;")
        out = out.replacingOccurrences(of: ">", with: "&gt;")
        out = out.replacingOccurrences(of: "\"", with: "&quot;")
        out = out.replacingOccurrences(of: "'", with: "&#39;")
        return out
    }

    private static func isoTimestamp(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }

    private static func sanitizeForFilename(_ raw: String) -> String {
        let lowered = raw.lowercased()
        var out = ""
        var lastWasDash = false
        for scalar in lowered.unicodeScalars {
            let c = Character(scalar)
            if c.isLetter || c.isNumber {
                out.append(c)
                lastWasDash = false
            } else if !lastWasDash {
                out.append("-")
                lastWasDash = true
            }
        }
        return out.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }

    private static func modalityInterventionTerm(_ modality: String) -> String {
        switch modality.lowercased() {
        case "radiation": return "radiation therapy"
        case "surgery": return "surgery"
        case "chemotherapy": return "chemotherapy"
        case "targeted": return "targeted therapy"
        default: return modality
        }
    }

    private static func stepRendering(_ state: AuditStep.State) -> (cssClass: String, label: String, detail: String?) {
        switch state {
        case .running: return ("step-running", "running", nil)
        case .done: return ("step-done", "done", nil)
        case .skipped(let reason): return ("step-skipped", "skipped", reason)
        case .failed(let message): return ("step-failed", "failed", message)
        }
    }

    // MARK: Stylesheet

    private static let stylesheet = """
    @page { margin: 0.6in; }
    body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
           font-size: 11pt; color: #1c1c1c; line-height: 1.45; margin: 0; padding: 0; }
    .report-header { border-bottom: 2px solid #333; padding-bottom: 8pt; margin-bottom: 14pt; }
    .report-header h1 { font-size: 20pt; margin: 0 0 4pt 0; }
    h2 { font-size: 13.5pt; margin-top: 18pt; margin-bottom: 8pt;
         border-bottom: 1px solid #999; padding-bottom: 3pt;
         page-break-after: avoid; }
    h3 { font-size: 11.5pt; margin-top: 14pt; margin-bottom: 6pt; page-break-after: avoid; }
    p { margin: 6pt 0; }
    .muted { color: #666; font-size: 9.5pt; }
    .section { page-break-inside: auto; margin-bottom: 6pt; }
    table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 10.5pt; }
    table.kv th { width: 28%; text-align: left; background: #f4f4f4;
                  padding: 5pt 8pt; border-bottom: 1px solid #ddd;
                  vertical-align: top; font-weight: 600; }
    table.kv td { padding: 5pt 8pt; border-bottom: 1px solid #ddd; vertical-align: top; }
    table.data th, table.data td { text-align: left; padding: 5pt 8pt;
                                    border-bottom: 1px solid #ddd; vertical-align: top; }
    table.data th { background: #f4f4f4; font-weight: 600; }
    ul, ol { padding-left: 22pt; margin: 6pt 0; }
    ul.plain { list-style: none; padding-left: 0; }
    ul.plain > li { margin: 3pt 0; }
    ul.references { margin-top: 4pt; padding-left: 18pt; }
    ul.references li { margin: 2pt 0; }
    code { font-family: ui-monospace, "SF Mono", Menlo, monospace;
           font-size: 9.5pt; background: #f4f4f4; padding: 1pt 4pt;
           border-radius: 3pt; }
    a { color: #1a5fb4; word-break: break-all; }
    .disclaimer { background: #fff8e1; border: 1px solid #f0c83a;
                  padding: 8pt 12pt; border-radius: 4pt; margin: 10pt 0;
                  font-size: 10.5pt; }
    .summary-block { background: #f6f9ff; border-left: 3px solid #4070d0;
                     padding: 8pt 12pt; margin: 10pt 0;
                     page-break-inside: avoid; }
    .summary-block .label { font-weight: 600; font-size: 10.5pt;
                            margin-bottom: 4pt; color: #2c5aaf; }
    .prose p { margin: 6pt 0; }
    .step-done { color: #1f7a1f; font-weight: 600; }
    .step-skipped { color: #666; font-weight: 600; }
    .step-failed { color: #b34d00; font-weight: 600; }
    .step-running { color: #4070d0; font-weight: 600; }
    .chip { display: inline-block; padding: 1pt 6pt; margin-left: 4pt;
            border-radius: 8pt; background: #eceff7; color: #4a4a4a;
            font-size: 9pt; }
    .footer { margin-top: 24pt; padding-top: 8pt;
              border-top: 1px solid #ccc; font-size: 9.5pt; color: #555; }
    .footer p { margin: 3pt 0; }
    h4 { font-size: 10.5pt; margin-top: 10pt; margin-bottom: 4pt; page-break-after: avoid; }
    .sev-severe { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
                  background: #fdecec; color: #b00020; font-weight: 600; font-size: 9pt; }
    .sev-moderate { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
                    background: #fff4e0; color: #a55400; font-weight: 600; font-size: 9pt; }
    .sev-minor { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
                 background: #fff9d6; color: #806300; font-weight: 600; font-size: 9pt; }
    .sev-unknown { display: inline-block; padding: 1pt 6pt; border-radius: 3pt;
                   background: #eceff7; color: #4a4a4a; font-weight: 600; font-size: 9pt; }
    """
}

// MARK: - Print completion target (Obj-C selector bridge)

/// NSObject shim that bridges NSPrintOperation's selector-based modal
/// completion (`printOperationDidRun:success:contextInfo:`) to a Swift
/// closure. NSPrintOperation does not retain its modal delegate, so the
/// caller is responsible for keeping this object alive until the callback
/// fires.
@MainActor
private final class PrintCompletionTarget: NSObject {
    private let completion: (Bool) -> Void

    init(completion: @escaping (Bool) -> Void) {
        self.completion = completion
        super.init()
    }

    @objc func printOperationDidRun(
        _ printOperation: NSPrintOperation,
        success: Bool,
        contextInfo: UnsafeMutableRawPointer?
    ) {
        completion(success)
    }
}

// MARK: - Coordinator (lifetime-scoped to the export call)

/// Bridges WKWebView's didFinish/didFail callbacks to a Swift continuation.
/// Held by the surrounding `withCheckedThrowingContinuation` closure for the
/// load's lifetime, which is enough to keep the WebView alive too.
private final class LoadCoordinator: NSObject, WKNavigationDelegate {
    var continuation: CheckedContinuation<Void, Error>?

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        continuation?.resume()
        continuation = nil
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: Error
    ) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}
