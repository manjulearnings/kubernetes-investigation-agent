from ..models import InvestigationReport, Severity


class MarkdownReporter:
    """Generates comprehensive GitHub/GitLab-flavored Markdown investigation reports."""

    def render(self, report: InvestigationReport) -> str:
        md = []

        # Title
        md.append(f"# 🛡️ Kubernetes Incident Investigation Report: `{report.incident_id}`\n")
        md.append(f"> **Generated at**: {report.timestamp} | **Duration**: {report.investigation_duration_ms}ms | **Log Source**: `{report.source_name}`\n")

        # Key Metrics Table
        md.append("## 📊 Incident Overview\n")
        md.append("| Metric | Value |")
        md.append("| :--- | :--- |")
        md.append(f"| **Incident ID** | `{report.incident_id}` |")
        md.append(f"| **Severity** | **{report.severity.value}** |")
        md.append(f"| **Confidence Score** | **{int(report.confidence_score * 100)}%** |")
        md.append(f"| **Primary Root Cause** | `{report.primary_root_cause}` |")
        md.append(f"| **Root Cause Category** | `{report.root_cause_category}` |")
        md.append(f"| **Total Log Lines** | {report.total_lines_analyzed} |")
        md.append(f"| **Errors / Warnings** | {report.error_count} errors / {report.warning_count} warnings |\n")

        # Executive Summary
        md.append("## 🔍 Executive Summary\n")
        md.append(f"{report.executive_summary}\n")

        # Detailed Findings
        if report.detailed_findings:
            md.append("### Key Findings\n")
            for finding in report.detailed_findings:
                md.append(f"- {finding}")
            md.append("")

        # Supporting Evidence Table
        md.append("## 🧾 Supporting Log Evidence\n")
        md.append("The following log lines provide direct empirical proof of the diagnosed condition:\n")
        md.append("| Line(s) | Timestamp | Pattern Matched | Evidence Snippet | Significance |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for ev in report.key_evidence:
            lines_str = ", ".join(str(l) for l in ev.line_numbers)
            ts = ev.timestamp or "N/A"
            clean_snippet = ev.log_snippet.replace("\n", " <br> ").replace("|", "\\|")
            md.append(f"| `{lines_str}` | `{ts}` | **{ev.pattern_matched}** | `{clean_snippet}` | {ev.relevance_explanation} |")
        md.append("")

        # Timeline
        if report.timeline:
            md.append("## ⏱️ Chronological Incident Timeline\n")
            md.append("| Timestamp / Line | Phase | Severity | Component | Event Description |")
            md.append("| :--- | :--- | :--- | :--- | :--- |")
            for t in report.timeline:
                ts = t.timestamp or f"Line {t.line_number}"
                comp = t.component or "pod/default"
                md.append(f"| `{ts}` | **{t.phase}** | `{t.severity.value}` | `{comp}` | {t.description} |")
            md.append("")

        # Detected Signals
        if report.signals:
            md.append("## 🚨 Detected Anomaly Signals\n")
            for sig in report.signals:
                md.append(f"### `{sig.signal_id}`: {sig.title} [{sig.severity.value}]")
                md.append(f"- **Category**: `{sig.category}`")
                md.append(f"- **Occurrences**: {sig.occurrence_count}")
                md.append(f"- **Impacted Scope**: `{sig.impact_scope or 'N/A'}`")
                md.append(f"- **First / Last Seen**: `{sig.first_seen}` -> `{sig.last_seen}`")
                md.append(f"- **Description**: {sig.description}\n")

        # Actionable Remediation Plan
        if report.remediation_plan:
            md.append("## 🛠️ Actionable Remediation & Kubectl Commands\n")
            for step in report.remediation_plan:
                md.append(f"### {step.phase}: {step.action}\n")
                md.append(f"{step.details}\n")
                if step.kubectl_command:
                    md.append("```bash")
                    md.append(step.kubectl_command)
                    md.append("```\n")

        return "\n".join(md)
