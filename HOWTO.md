# 📖 How-To Guide & Usage Recipes

Welcome to the **Kubernetes Investigation Agent** practical guide! This document provides real-world recipes, copy-paste commands, and workflows for Site Reliability Engineers (SREs), DevOps practitioners, and platform engineers.

---

## 📑 Table of Contents

1. [⚡ Quick Start Checklist](#-quick-start-checklist)
2. [Recipe 1: Offline / Local Log Analysis (Air-Gapped)](#recipe-1-offline--local-log-analysis-air-gapped)
3. [Recipe 2: Live On-Call SRE Debugging (kubectl piping)](#recipe-2-live-on-call-sre-debugging-kubectl-piping)
4. [Recipe 3: Generating Reports (Terminal, Markdown, JSON)](#recipe-3-generating-reports-terminal-markdown-json)
5. [Recipe 4: AI-Powered Deep Diagnosis with Google Gemini](#recipe-4-ai-powered-deep-diagnosis-with-google-gemini)
6. [Recipe 5: Python SDK & CI/CD Integration](#recipe-5-python-sdk--cicd-integration)
7. [Recipe 6: Batch Analyzing Multiple Log Files](#recipe-6-batch-analyzing-multiple-log-files)
8. [🎛️ CLI Options & Flags Reference](#️-cli-options--flags-reference)
9. [❓ Frequently Asked Questions (FAQ)](#-frequently-asked-questions-faq)

---

## ⚡ Quick Start Checklist

### 1. Clone & Set Up Virtual Environment

#### On Windows (PowerShell)
```powershell
git clone https://github.com/manjulearnings/k8s-investigation-agent.git
cd k8s-investigation-agent
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
```

#### On Linux / macOS (Bash / Zsh)
```bash
git clone https://github.com/manjulearnings/k8s-investigation-agent.git
cd k8s-investigation-agent
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Verify Installation
```bash
k8s-agent --help
```
*(Or invoke directly via Python module: `python -m k8s_agent.cli --help`)*

### 3. 🎯 30-Second Test Drive (No cluster or API key required!)
Run this command right now to test the agent on a bundled crash log:
```bash
k8s-agent sample_logs/01_crashloop_oom.log
```
You will immediately see the formatted terminal report with root-cause deduction, confidence score, and remediation steps!

---

## Recipe 1: Offline / Local Log Analysis (Air-Gapped)

> **Use Case:** Analyzing exported pod logs, incident archives, or troubleshooting in an isolated network with **zero cloud credentials, zero API keys, and zero network access**.

### Analyze a single log file:
```bash
k8s-agent sample_logs/01_crashloop_oom.log
```

### Try bundled real-world incident samples:
```bash
# 1. Out Of Memory (OOMKilled - Exit Code 137) with CrashLoopBackOff
k8s-agent sample_logs/01_crashloop_oom.log

# 2. Database connection refused & network socket failure
k8s-agent sample_logs/02_db_connection_refused.log

# 3. CoreDNS resolution failure & missing ConfigMap key
k8s-agent sample_logs/03_dns_and_config_missing.log

# 4. Kubernetes RBAC 403 Forbidden permission denied
k8s-agent sample_logs/04_rbac_permission_denied.log

# 5. Ingress TLS x509 certificate expired
k8s-agent sample_logs/05_tls_cert_expired.log

# 6. Custom application stack trace (Python Stripe API failure)
k8s-agent sample_logs/06_custom_payment_stripe_error.log
```

### What You Will See in the Output:
When you run any investigation, the agent automatically organizes findings into four structured sections:
1. **Incident Overview**: Severity badge (`CRITICAL`, `HIGH`, `MEDIUM`), Confidence %, and Primary Root Cause.
2. **Empirical Supporting Evidence**: Exact line numbers, timestamps, and verbatim code/log snippets.
3. **Chronological Incident Timeline**: Traces the incident from *Inception* → *Cascading Failure* → *Kubelet Intervention*.
4. **Remediation Plan**: Tailored, copy-pasteable `kubectl` commands to fix the issue immediately.

---

## Recipe 2: Live On-Call SRE Debugging (kubectl piping)

> **Use Case:** An engineer is on-call, alerted to a crashing or degraded pod, and wants instant root-cause analysis without manually scrolling through hundreds of log lines.

### Stream live logs directly from `kubectl`:
```bash
# Stream previous crashed container instance:
kubectl logs pod/checkout-service-7bb8c57657-69vsd -n prod --previous | k8s-agent -

# Tail live failing logs (last 300 lines):
kubectl logs deployment/payment-processor -n billing --tail=300 | k8s-agent -

# Investigate a specific container in a multi-container pod:
kubectl logs pod/ingress-gateway-84f98c64d-xzk2q -c envoy-proxy --previous | k8s-agent -
```

> 💡 **Why the trailing dash (`-`)?**  
> In command-line conventions, `-` tells the agent: *"Read incoming logs from standard input (stdin) rather than looking for a file on disk."* This is what allows piping live logs directly from `kubectl`!

### Ingest Kubernetes Cluster Events:
```bash
# Ingest recent cluster events to diagnose scheduling or image pull failures:
kubectl get events -n default --sort-by='.metadata.creationTimestamp' | k8s-agent -
```

---

## Recipe 3: Generating Reports (Terminal, Markdown, JSON)

> **Use Case:** Automatically generate structured diagnostic reports for team communication, ticketing systems, or automated SIEM/monitoring pipelines.

### 1. Interactive Terminal Output (Default)
Displays rich colored severity banners, causal timelines, empirical evidence snippets, and immediate remediation steps:
```bash
k8s-agent sample_logs/02_db_connection_refused.log
```

### 2. Generate Markdown for Jira / GitHub / Slack
Export a formatted Markdown report to paste directly into an incident ticket or GitHub Issue:
```bash
# Output markdown directly to a file:
k8s-agent sample_logs/01_crashloop_oom.log -f markdown -o incident_report.md
```

### 3. Generate Machine-Readable JSON for Webhooks & CI/CD
Output structured JSON for ingestion into Datadog, Splunk, PagerDuty, or ServiceNow:
```bash
k8s-agent sample_logs/03_dns_and_config_missing.log -f json -o incident.json
```

---

## Recipe 4: AI-Powered Deep Diagnosis with Google Gemini

> **Use Case:** When an incident is caused by an unclassified application bug or custom stack trace (Python, Java, Go, Node.js) rather than standard infrastructure errors, let Google Gemini diagnose the code and explain the exact fix.

### 1. Configure Gemini API Key

**Via Environment Variable (Recommended):**
```bash
# Linux / macOS:
export GEMINI_API_KEY="AIzaSy..."

# Windows PowerShell:
$env:GEMINI_API_KEY="AIzaSy..."
```

**Via CLI Flag:**
```bash
k8s-agent sample_logs/06_custom_payment_stripe_error.log --gemini-api-key="your-api-key"
```

### 2. Run Investigation with Gemini AI

```bash
# Automatically invokes Gemini when an unclassified code exception is detected:
k8s-agent sample_logs/06_custom_payment_stripe_error.log

# Force Gemini AI analysis even for standard known Kubernetes errors:
k8s-agent sample_logs/01_crashloop_oom.log --force-gemini
```

### 3. Select Gemini Model

```bash
# Specify model version (default: gemini-3.8-flash):
k8s-agent app.log --gemini-model="gemini-3.8-flash"

# Automatically query Google AI Studio for the newest available flash model:
k8s-agent app.log --gemini-model="latest"
```

---

## Recipe 5: Python SDK & CI/CD Integration

> **Use Case:** Embedding Kubernetes failure diagnostics into your own automated Python services, custom Slack bots, or CI/CD deployment pipelines.

### Programmatic Python Usage:
```python
from pathlib import Path
from k8s_agent import KubernetesInvestigationAgent

# 1. Initialize the agent
agent = KubernetesInvestigationAgent()

# 2. Run investigation
report = agent.investigate_file(Path("sample_logs/01_crashloop_oom.log"))

# 3. Access structured properties
print(f"Incident ID : {report.incident_id}")
print(f"Severity    : {report.severity.value}")
print(f"Root Cause  : {report.primary_root_cause}")
print(f"Category    : {report.root_cause_category}")
print(f"Confidence  : {report.confidence_score * 100:.0f}%")

print("\nKey Supporting Evidence:")
for ev in report.key_evidence:
    print(f" - [Line {ev.line_numbers}] {ev.relevance_explanation}")

print("\nRemediation Actions:")
for step in report.remediation_plan:
    print(f" - [{step.phase}] {step.action}")
    if step.kubectl_command:
        print(f"   Command: {step.kubectl_command}")
```

### CI/CD Deployment Verification (GitHub Actions / GitLab CI):
```bash
# Run post-deployment smoke test and export report:
kubectl logs deployment/catalog-service -n staging --previous | k8s-agent - -f json -o report.json

# Fail CI/CD build if severity is CRITICAL or HIGH:
python -c "import json; r=json.load(open('report.json')); exit(1 if r['severity'] in ['CRITICAL', 'HIGH'] else 0)"
```

---

## Recipe 6: Batch Analyzing Multiple Log Files

> **Use Case:** Investigate an entire directory of crash dumps and export an incident markdown report for each.

### Bash / Linux / macOS:
```bash
for log_file in sample_logs/*.log; do
    echo "Investigating $log_file..."
    k8s-agent "$log_file" -f markdown -o "${log_file%.log}_report.md"
done
```

### PowerShell / Windows:
```powershell
Get-ChildItem -Path sample_logs\*.log | ForEach-Object {
    Write-Host "Investigating $($_.Name)..."
    k8s-agent $_.FullName -f markdown -o "$($_.FullName)_report.md"
}
```

---

## 🎛️ CLI Options & Flags Reference

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Log Source** | `[log_source]` | Path to log file, or `-` for stdin pipe | `-` (stdin) |
| **Output Format** | `-f, --format` | `terminal`, `markdown`, `json` | `terminal` |
| **Output File** | `-o, --output` | File path to write the formatted report | `stdout` |
| **Gemini API Key** | `--gemini-api-key` | Google Gemini API key | `$GEMINI_API_KEY` |
| **Gemini Model** | `--gemini-model` | Gemini model name or `latest` | `gemini-3.8-flash` |
| **Force Gemini** | `--force-gemini` | Force Gemini AI diagnosis for all errors | `False` |

---

## ❓ Frequently Asked Questions (FAQ)

### Q: Do I need a Google Gemini API key to use this?
**No.** Offline file analysis, sample logs, and stdin pipes work completely air-gapped without any API keys, accounts, or network access. Standard failure patterns (OOM, DB connection, DNS, RBAC, TLS, Disk Full) are detected deterministically in <5ms locally.

### Q: Does this send my logs to the internet?
**No.** All deterministic failure analysis runs 100% locally on your machine. Network calls only occur if you explicitly provide a `GEMINI_API_KEY` to diagnose unclassified code stack traces.

### Q: What operating systems and shells are supported?
The agent runs identically on **Windows PowerShell**, **Command Prompt**, **Linux (Bash/Zsh)**, and **macOS Terminal**.

### Q: How does this differ from the `aks-investigation-agent`?
- **`k8s-investigation-agent`** is cloud-agnostic, built for any Kubernetes cluster (Minikube, Kind, Bare Metal, GKE, EKS, K3s), with Google Gemini AI for code debugging.
- **`aks-investigation-agent`** is specifically tailored for Microsoft Azure Kubernetes Service (AKS), featuring Azure Monitor / Log Analytics KQL ingestion, Azure OpenAI (GPT-4o), and Microsoft Teams Adaptive Cards.
