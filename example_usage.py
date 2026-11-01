"""Example demonstrating programmatic usage of the Kubernetes Investigation Agent."""

from pathlib import Path
from k8s_agent import KubernetesInvestigationAgent


def run_example():
    # Initialize the agent
    agent = KubernetesInvestigationAgent()

    # Path to sample log file
    sample_path = Path(__file__).parent / "sample_logs" / "02_db_connection_refused.log"
    print(f"Investigating log file: {sample_path.name} ...\n")

    # Perform investigation
    report = agent.investigate_file(sample_path)

    # 1. Inspect Structured Report Data
    print(f"Incident ID        : {report.incident_id}")
    print(f"Severity           : {report.severity.value}")
    print(f"Confidence Score   : {int(report.confidence_score * 100)}%")
    print(f"Primary Root Cause : {report.primary_root_cause}")
    print(f"Category           : {report.root_cause_category}")
    print(f"Errors Found       : {report.error_count}")
    print(f"Lines Analyzed     : {report.total_lines_analyzed}")

    print("\n--- Key Supporting Evidence ---")
    for ev in report.key_evidence[:3]:
        lines = ", ".join(str(l) for l in ev.line_numbers)
        print(f"[Line {lines}] {ev.relevance_explanation}")
        print(f"  Snippet: {ev.log_snippet[:120]}...\n")

    print("--- Remediation Actions ---")
    for step in report.remediation_plan:
        print(f"* [{step.phase}] {step.action}")
        if step.kubectl_command:
            print(f"    Command: {step.kubectl_command.splitlines()[0]}")

    print("\n" + "=" * 60)
    print("Printing Rich Terminal Report:")
    print("=" * 60)
    agent.print_terminal_report(report)


if __name__ == "__main__":
    run_example()
