from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from ..models import InvestigationReport, Severity


class TerminalReporter:
    """Renders investigation reports with rich formatting, color-coded badges, and tables."""

    def __init__(self, console: Console = None):
        import sys
        if console is None:
            # Safe utf-8 handling
            if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
                try:
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            self.console = Console()
        else:
            self.console = console

    def render(self, report: InvestigationReport):
        # 1. Header Banner
        severity_color = self._severity_color(report.severity)
        header_text = Text()
        header_text.append(f"KUBERNETES INCIDENT INVESTIGATION REPORT\n", style="bold white")
        header_text.append(f"Incident ID: ", style="bold")
        header_text.append(f"{report.incident_id}  ", style="cyan bold")
        header_text.append(f"Severity: ", style="bold")
        header_text.append(f"[{report.severity.value}]  ", style=f"bold {severity_color}")
        header_text.append(f"Confidence: ", style="bold")
        header_text.append(f"{int(report.confidence_score * 100)}%  ", style="green bold")
        header_text.append(f"Duration: ", style="bold")
        header_text.append(f"{report.investigation_duration_ms} ms", style="dim")

        self.console.print(Panel(header_text, border_style=severity_color, box=box.ROUNDED))

        # 2. Executive Summary Panel
        summary_panel = Panel(
            f"[bold]Primary Root Cause:[/bold] [bold {severity_color}]{report.primary_root_cause}[/bold {severity_color}]\n"
            f"[bold]Category:[/bold] `{report.root_cause_category}`\n\n"
            f"{report.executive_summary}\n\n"
            f"[dim]Total Lines Analyzed: {report.total_lines_analyzed} | Errors: {report.error_count} | Warnings: {report.warning_count}[/dim]",
            title="🔍 Executive Summary & Root Cause Analysis",
            border_style="cyan",
            box=box.ROUNDED,
        )
        self.console.print(summary_panel)

        # 3. Key Supporting Evidence Table
        if report.key_evidence:
            ev_table = Table(
                title="🧾 Supporting Log Evidence (Verbatim Proof)",
                box=box.ROUNDED,
                header_style="bold magenta",
                show_lines=True,
            )
            ev_table.add_column("Line(s)", style="bold cyan", width=10)
            ev_table.add_column("Timestamp", style="dim", width=22)
            ev_table.add_column("Evidence Snippet", style="white")
            ev_table.add_column("Significance / Match", style="yellow", width=34)

            for ev in report.key_evidence:
                lines_str = ",".join(str(l) for l in ev.line_numbers)
                ts_str = ev.timestamp or "N/A"
                snippet = ev.log_snippet.strip()
                if len(snippet) > 220:
                    snippet = snippet[:220] + "..."
                ev_table.add_row(
                    lines_str,
                    ts_str,
                    f"[italic]{snippet}[/italic]",
                    f"{ev.pattern_matched}\n[dim]{ev.relevance_explanation}[/dim]",
                )
            self.console.print(ev_table)

        # 4. Failure Sequence Timeline
        if report.timeline:
            tl_table = Table(
                title="⏱️ Chronological Failure Timeline",
                box=box.ROUNDED,
                header_style="bold blue",
            )
            tl_table.add_column("Time / Line", style="dim", width=18)
            tl_table.add_column("Phase", style="bold", width=22)
            tl_table.add_column("Sev", width=8)
            tl_table.add_column("Component", style="cyan", width=20)
            tl_table.add_column("Event Description", style="white")

            for t in report.timeline:
                sev_style = self._severity_color(t.severity)
                tl_table.add_row(
                    f"{t.timestamp or f'Line {t.line_number}'}",
                    f"[bold]{t.phase}[/bold]",
                    f"[{sev_style}]{t.severity.value}[/{sev_style}]",
                    t.component or "pod/app",
                    t.description,
                )
            self.console.print(tl_table)

        # 5. Actionable Remediation Plan
        if report.remediation_plan:
            rem_table = Table(
                title="🛠️ Actionable Remediation Plan & Kubectl Commands",
                box=box.ROUNDED,
                header_style="bold green",
                show_lines=True,
            )
            rem_table.add_column("Phase", style="bold", width=24)
            rem_table.add_column("Recommended Action", style="white", width=36)
            rem_table.add_column("Suggested Command(s) / Config", style="green")

            for step in report.remediation_plan:
                cmd = step.kubectl_command or "[dim]No direct command required[/dim]"
                rem_table.add_row(
                    step.phase,
                    f"{step.action}\n[dim]{step.details}[/dim]",
                    cmd,
                )
            self.console.print(rem_table)

    def _severity_color(self, severity: Severity) -> str:
        mapping = {
            Severity.CRITICAL: "bold red",
            Severity.HIGH: "bold orange3",
            Severity.MEDIUM: "bold yellow",
            Severity.LOW: "bold blue",
            Severity.INFO: "bold green",
        }
        return mapping.get(severity, "white")
