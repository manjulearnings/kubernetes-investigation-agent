import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows terminals
if sys.stdout.encoding != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr.encoding != "utf-8" and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from .agent import KubernetesInvestigationAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="k8s-agent",
        description="Kubernetes Investigation Agent: Analyzes Kubernetes logs, determines root causes, and delivers evidence-backed diagnostic reports.",
    )
    parser.add_argument(
        "log_source",
        nargs="?",
        default="-",
        help="Path to Kubernetes log file, or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["terminal", "markdown", "json"],
        default="terminal",
        help="Output format: 'terminal' (rich interactive CLI), 'markdown' (for docs/issues), or 'json' (machine readable).",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Optional path to write the output report (e.g., incident_report.md or report.json).",
    )
    parser.add_argument(
        "--gemini-api-key",
        type=str,
        default=None,
        help="Google Gemini API key (or set environment variable GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=None,
        help="Gemini model to use (default: gemini-2.0-flash, or pass 'latest' for auto-discovery).",
    )
    parser.add_argument(
        "--force-gemini",
        action="store_true",
        help="Force Gemini AI diagnosis even for standard known Kubernetes errors.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    console = Console(stderr=True)

    agent = KubernetesInvestigationAgent(
        gemini_api_key=args.gemini_api_key,
        gemini_model=args.gemini_model,
        force_gemini=args.force_gemini,
    )

    # Read from file or stdin
    try:
        if args.log_source == "-":
            if sys.stdin.isatty():
                console.print("[yellow]Reading logs from standard input. Paste logs and press Ctrl+Z (Windows) or Ctrl+D (Unix) to finish:[/yellow]")
            log_input = sys.stdin.read()
            source_name = "stdin"
        else:
            log_path = Path(args.log_source)
            if not log_path.exists():
                console.print(f"[bold red]Error:[/bold red] Log file '{args.log_source}' does not exist.")
                sys.exit(1)
            log_input = log_path
            source_name = log_path.name

        report = agent.investigate(log_input, source_name=source_name)

        # Output formatting
        if args.format == "terminal":
            if args.output:
                # If writing terminal format to file, write markdown instead
                content = agent.to_markdown(report)
                Path(args.output).write_text(content, encoding="utf-8")
                console.print(f"[bold green]Report saved to:[/bold green] {args.output}")
            else:
                agent.print_terminal_report(report)
        elif args.format == "markdown":
            md_output = agent.to_markdown(report)
            if args.output:
                Path(args.output).write_text(md_output, encoding="utf-8")
                console.print(f"[bold green]Markdown report saved to:[/bold green] {args.output}")
            else:
                sys.stdout.write(md_output + "\n")
        elif args.format == "json":
            json_output = agent.to_json(report)
            if args.output:
                Path(args.output).write_text(json_output, encoding="utf-8")
                console.print(f"[bold green]JSON report saved to:[/bold green] {args.output}")
            else:
                sys.stdout.write(json_output + "\n")

    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        console.print(f"[bold red]Investigation failed:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
