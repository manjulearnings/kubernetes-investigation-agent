import os
import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from .models import InvestigationReport, RemediationStep, Severity

logger = logging.getLogger(__name__)

# Preferred generation models ordered from newest to stable fallback
PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3-flash",
]
DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiInvestigator:
    """Smart Google Gemini AI integration for Kubernetes incident diagnosis.

    Uses Google's official Gemini API to diagnose ANY unknown, custom, or complex
    application failure that is not present in predefined rule catalogs.
    Auto-discovers and defaults to the latest generation Gemini models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        # Allows explicit model, env variable, or default to modern 2.0-flash
        raw_model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self.model = self._resolve_model(raw_model)

    def is_available(self) -> bool:
        """Returns True if a Gemini API key is configured."""
        return bool(self.api_key)

    def _resolve_model(self, requested_model: str) -> str:
        """Resolves 'latest' or 'auto' to the newest available Gemini model on the account."""
        if requested_model in ("latest", "auto") and self.is_available():
            discovered = self._discover_latest_model()
            if discovered:
                return discovered
            return DEFAULT_MODEL
        return requested_model

    def _discover_latest_model(self) -> Optional[str]:
        """Queries Google's API to dynamically discover the newest available Flash model."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
            with httpx.Client(timeout=5.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                    # Check in order of newest preferred models
                    for candidate in PREFERRED_MODELS:
                        if candidate in models:
                            logger.info(f"Dynamically resolved latest Gemini model to: {candidate}")
                            return candidate
        except Exception as e:
            logger.debug(f"Dynamic model discovery failed: {e}. Defaulting to {DEFAULT_MODEL}")
        return None

    def diagnose_unknown_failure(self, report: InvestigationReport) -> InvestigationReport:
        """Consults Gemini to diagnose an unclassified or custom application error."""
        if not self.is_available():
            return report

        # Extract context from evidence and timeline
        evidence_texts = []
        for ev in report.key_evidence[:5]:
            lines = ",".join(str(l) for l in ev.line_numbers)
            evidence_texts.append(f"Line {lines} [{ev.timestamp or 'N/A'}]:\n{ev.log_snippet}")
        evidence_block = "\n---\n".join(evidence_texts)

        prompt = f"""You are an elite Kubernetes Site Reliability Engineer (SRE).
The Kubernetes investigation engine parsed this incident from container logs, but found an unclassified or custom application failure not covered by standard Kubernetes infrastructure signatures.

INCIDENT METRICS:
- Source: {report.source_name}
- Total Lines: {report.total_lines_analyzed}
- Errors Found: {report.error_count}
- Initial Classification: {report.primary_root_cause} ({report.root_cause_category})

EXACT LOG EVIDENCE & STACK TRACES:
{evidence_block}

CHRONOLOGICAL TIMELINE:
{chr(10).join([f"- [{t.timestamp}] ({t.phase}) {t.description}" for t in report.timeline[:6]])}

TASK:
Analyze the exact error messages and stack traces above. Determine:
1. What exact code or configuration bug caused this crash.
2. Formulate a concise, highly specific Root Cause Title.
3. Formulate an actionable executive summary explaining the exact failure mechanism.
4. Provide a structured 3-phase remediation plan with exact commands or code fixes.

Respond strictly with a JSON object in this exact schema:
{{
  "root_cause_title": "<Specific Diagnosis, e.g. 'Stripe API Authentication Failure (Missing API Key)'>",
  "category": "<Short category code, e.g. 'PAYMENT_AUTH_ERROR' or 'DATABASE_SCHEMA_MISMATCH'>",
  "confidence_score": 0.95,
  "executive_summary": "<2-3 sentence executive summary explaining what broke, why, and impact>",
  "remediation_plan": [
    {{
      "phase": "Phase 1: Immediate Mitigation",
      "action": "<What to do immediately to restore service>",
      "kubectl_command": "<Optional copy-pasteable kubectl command or config, or null>",
      "details": "<Technical detail explaining why this works>"
    }},
    {{
      "phase": "Phase 2: Root Cause Fix",
      "action": "<Code or secret fix to permanently resolve the issue>",
      "kubectl_command": "<Optional copy-pasteable kubectl command or config, or null>",
      "details": "<Exact fix details, e.g. which environment variable or secret to add>"
    }},
    {{
      "phase": "Phase 3: Long-Term Prevention",
      "action": "<Guardrail or CI/CD check to prevent recurrence>",
      "kubectl_command": null,
      "details": "<Prevention guidance>"
    }}
  ]
}}
"""

        try:
            ai_data = self._call_gemini_json_with_fallback(prompt)
            if ai_data:
                # Update report with Gemini's specialized diagnosis
                if "root_cause_title" in ai_data and ai_data["root_cause_title"]:
                    report.primary_root_cause = f"✨ {ai_data['root_cause_title']}"
                if "category" in ai_data and ai_data["category"]:
                    report.root_cause_category = ai_data["category"]
                if "confidence_score" in ai_data and isinstance(ai_data["confidence_score"], (int, float)):
                    report.confidence_score = float(ai_data["confidence_score"])
                if "executive_summary" in ai_data and ai_data["executive_summary"]:
                    report.executive_summary = (
                        f"[Gemini AI SRE Diagnosis]\n"
                        f"{ai_data['executive_summary']}\n\n"
                        f"Analyzed {report.error_count} error log line(s) using {self.model}."
                    )
                if "remediation_plan" in ai_data and isinstance(ai_data["remediation_plan"], list):
                    new_plan = []
                    for step in ai_data["remediation_plan"]:
                        new_plan.append(
                            RemediationStep(
                                phase=step.get("phase", "Remediation"),
                                action=step.get("action", "Inspect and fix error"),
                                kubectl_command=step.get("kubectl_command"),
                                details=step.get("details", ""),
                            )
                        )
                    if new_plan:
                        report.remediation_plan = new_plan

                report.detailed_findings.append(
                    f"**Gemini AI Diagnosis**: Successfully analyzed custom application stack trace using `{self.model}`."
                )

        except Exception as e:
            logger.warning(f"Gemini API request failed: {e}. Falling back to deterministic diagnosis.")
            report.detailed_findings.append(
                f"**Gemini AI Note**: AI analysis skipped ({e}). Report backed by deterministic rules."
            )

        return report

    def _call_gemini_json_with_fallback(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Calls Gemini API, trying primary model first and falling back if unavailable."""
        models_to_try = [self.model]
        for fallback in PREFERRED_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        for attempt_model in models_to_try:
            result = self._call_single_model(attempt_model, prompt)
            if result is not None:
                self.model = attempt_model
                return result
        return None

    def _call_single_model(self, model_name: str, prompt: str) -> Optional[Dict[str, Any]]:
        """Makes direct HTTP request to a specific Gemini model."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        try:
            with httpx.Client(timeout=25.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if raw_text:
                            return json.loads(raw_text.strip())
                elif response.status_code == 404:
                    logger.warning(f"Model {model_name} returned 404 Not Found. Trying fallback model...")
                    return None
                else:
                    logger.warning(f"Gemini API ({model_name}) returned status {response.status_code}: {response.text}")
                    return None
        except Exception as e:
            logger.warning(f"Request to {model_name} failed: {e}")
            return None
        return None
