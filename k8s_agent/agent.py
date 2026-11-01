import os
from pathlib import Path
from typing import Union, Optional, TextIO
from .models import InvestigationReport
from .parser import KubernetesLogParser
from .engine import InvestigationEngine
from .gemini import GeminiInvestigator
from .reporters import TerminalReporter, MarkdownReporter, JSONReporter


class KubernetesInvestigationAgent:
    """Smart Hybrid Kubernetes Investigation Agent.

    Combines an instant deterministic rule engine with optional Google Gemini AI
    to diagnose any failure—from standard infrastructure incidents to custom,
    unclassified application errors and stack traces.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        force_gemini: bool = False,
    ):
        self.parser = KubernetesLogParser()
        self.engine = InvestigationEngine()
        self.gemini = GeminiInvestigator(api_key=gemini_api_key, model=gemini_model)
        self.force_gemini = force_gemini
        self.terminal_reporter = TerminalReporter()
        self.markdown_reporter = MarkdownReporter()
        self.json_reporter = JSONReporter()

    def investigate(
        self,
        log_input: Union[str, Path, TextIO],
        source_name: Optional[str] = None,
    ) -> InvestigationReport:
        """Performs end-to-end investigation of Kubernetes logs.

        Args:
            log_input: File path, raw log string, or file-like stream.
            source_name: Optional friendly name for the log source (e.g., 'checkout-service.log').

        Returns:
            InvestigationReport containing root cause, timeline, and exact supporting evidence.
        """
        raw_text, detected_source = self._load_log_content(log_input)
        effective_source = source_name or detected_source

        # 1. Parse into structured entries
        entries = self.parser.parse_text(raw_text)

        # 2. Perform Root Cause Analysis & Signal Extraction
        report = self.engine.analyze(entries, source_name=effective_source)

        # 3. Smart Gemini AI Fallback / Enhancement:
        # If this is an unclassified application error or runtime panic, invoke Gemini:
        if self.gemini.is_available():
            if report.root_cause_category in ("APPLICATION_ERROR", "APPLICATION_PANIC") or self.force_gemini:
                report = self.gemini.diagnose_unknown_failure(report)
        elif report.root_cause_category in ("APPLICATION_ERROR", "APPLICATION_PANIC"):
            # Inform user how to unlock AI analysis for unclassified errors
            report.detailed_findings.append(
                "💡 **AI Tip**: This application exception was detected from the stack trace. "
                "Set GEMINI_API_KEY to let Google Gemini AI analyze the code failure and generate tailored code/kubectl fixes."
            )

        return report

    def investigate_file(self, filepath: Union[str, Path]) -> InvestigationReport:
        """Convenience method to investigate a specific log file on disk."""
        path_obj = Path(filepath)
        if not path_obj.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        return self.investigate(path_obj, source_name=path_obj.name)

    def print_terminal_report(self, report: InvestigationReport):
        """Prints a styled Rich terminal report."""
        self.terminal_reporter.render(report)

    def to_markdown(self, report: InvestigationReport) -> str:
        """Returns the report formatted as Markdown."""
        return self.markdown_reporter.render(report)

    def to_json(self, report: InvestigationReport) -> str:
        """Returns the report serialized as JSON."""
        return self.json_reporter.render(report)

    def _load_log_content(self, log_input: Union[str, Path, TextIO]) -> tuple[str, str]:
        """Resolves log content and its source identifier."""
        if isinstance(log_input, Path):
            return log_input.read_text(encoding="utf-8", errors="replace"), log_input.name

        if isinstance(log_input, str):
            # Check if it points to an existing file
            if len(log_input) < 1024 and ("\n" not in log_input) and os.path.exists(log_input):
                p = Path(log_input)
                return p.read_text(encoding="utf-8", errors="replace"), p.name
            return log_input, "raw_log_input"

        if hasattr(log_input, "read"):
            name = getattr(log_input, "name", "stream_input")
            return log_input.read(), name

        raise ValueError(f"Unsupported log input type: {type(log_input)}")
