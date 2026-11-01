import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from .models import (
    LogEntry,
    LogLevel,
    Severity,
    Evidence,
    InvestigationSignal,
    TimelineEvent,
    RemediationStep,
    InvestigationReport,
)
from .patterns import K8S_SIGNATURES, FailureSignature


class InvestigationEngine:
    """Core deterministic diagnostic and correlation engine for Kubernetes logs."""

    def __init__(self):
        self.signatures = K8S_SIGNATURES

    def analyze(self, entries: List[LogEntry], source_name: str = "kubernetes_log_stream") -> InvestigationReport:
        """Executes full diagnostic analysis over parsed log entries."""
        start_time = datetime.now()

        # Step 1: Scan and detect matching failure signatures
        matched_signals_map: Dict[str, InvestigationSignal] = {}
        candidate_causes: List[Tuple[FailureSignature, Evidence, LogEntry]] = []
        error_count = 0
        warning_count = 0

        for entry in entries:
            if entry.level in (LogLevel.ERROR, LogLevel.FATAL, LogLevel.CRITICAL):
                error_count += 1
            elif entry.level in (LogLevel.WARN, LogLevel.WARNING):
                warning_count += 1

            # Match against known failure signatures
            for sig in self.signatures:
                matched_snippet = sig.matches(entry.raw_text)
                if not matched_snippet and entry.stack_trace:
                    matched_snippet = sig.matches(entry.stack_trace)

                if matched_snippet:
                    evidence = Evidence(
                        line_numbers=[entry.line_number],
                        timestamp=entry.timestamp_str or (entry.timestamp.isoformat() if entry.timestamp else None),
                        log_snippet=entry.stack_trace if entry.stack_trace else entry.raw_text.strip(),
                        relevance_explanation=f"Directly matches {sig.title}: '{matched_snippet}'",
                        pattern_matched=sig.title,
                        confidence=0.95 if entry.stack_trace else 0.90,
                    )

                    candidate_causes.append((sig, evidence, entry))

                    # Group into InvestigationSignal
                    if sig.signature_id not in matched_signals_map:
                        matched_signals_map[sig.signature_id] = InvestigationSignal(
                            signal_id=sig.signature_id,
                            category=sig.category,
                            title=sig.title,
                            severity=sig.severity,
                            description=sig.description,
                            first_seen=evidence.timestamp,
                            last_seen=evidence.timestamp,
                            occurrence_count=1,
                            evidences=[evidence],
                            impact_scope=entry.component or "unknown",
                        )
                    else:
                        sig_obj = matched_signals_map[sig.signature_id]
                        sig_obj.occurrence_count += 1
                        sig_obj.last_seen = evidence.timestamp
                        if len(sig_obj.evidences) < 10:  # Cap evidence per signal to prevent clutter
                            sig_obj.evidences.append(evidence)
                        if entry.component and entry.component not in (sig_obj.impact_scope or ""):
                            sig_obj.impact_scope = f"{sig_obj.impact_scope}, {entry.component}"

        # Collect all detected component names across entries
        detected_components = []
        for e in entries:
            if e.component and e.component not in detected_components:
                detected_components.append(e.component)
        primary_component = detected_components[0] if detected_components else None

        # Backfill unknown impact_scopes if we detected a component in the stream
        if primary_component:
            for s in matched_signals_map.values():
                if s.impact_scope in ("unknown", None, ""):
                    s.impact_scope = primary_component

        # Step 2: Determine Primary Root Cause vs Cascading Symptoms
        primary_sig, primary_evidence, confidence = self._deduce_primary_root_cause(candidate_causes, entries)

        # Step 3: Build Chronological Timeline
        timeline = self._build_timeline(candidate_causes, entries, primary_sig)

        # Step 4: Extract Key Evidences across findings
        key_evidence: List[Evidence] = []
        if primary_evidence:
            key_evidence.append(primary_evidence)
        for sig_obj in matched_signals_map.values():
            for ev in sig_obj.evidences:
                if ev not in key_evidence and len(key_evidence) < 8:
                    key_evidence.append(ev)

        # Step 5: Generate Remediation Plan with concrete names if detected
        remediation_plan = self._generate_remediations(primary_sig, matched_signals_map, primary_component)

        # Step 6: Determine Overall Incident Severity
        overall_severity = Severity.INFO
        if any(s.severity == Severity.CRITICAL for s in matched_signals_map.values()):
            overall_severity = Severity.CRITICAL
        elif any(s.severity == Severity.HIGH for s in matched_signals_map.values()) or error_count > 0:
            overall_severity = Severity.HIGH
        elif any(s.severity == Severity.MEDIUM for s in matched_signals_map.values()) or warning_count > 0:
            overall_severity = Severity.MEDIUM

        # Step 7: Formulate Executive Summary & Detailed Findings
        primary_title = primary_sig.title if primary_sig else "Unclassified Anomaly / Errors Present"
        primary_cat = primary_sig.category if primary_sig else "UNKNOWN"
        summary = self._formulate_summary(primary_sig, primary_evidence, matched_signals_map, error_count)
        detailed_findings = self._formulate_detailed_findings(primary_sig, matched_signals_map, error_count, warning_count)

        duration = (datetime.now() - start_time).total_seconds() * 1000

        return InvestigationReport(
            incident_id=f"INC-K8S-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
            source_name=source_name,
            total_lines_analyzed=len(entries),
            error_count=error_count,
            warning_count=warning_count,
            severity=overall_severity,
            primary_root_cause=primary_title,
            root_cause_category=primary_cat,
            confidence_score=confidence,
            executive_summary=summary,
            detailed_findings=detailed_findings,
            signals=list(matched_signals_map.values()),
            timeline=timeline,
            key_evidence=key_evidence,
            remediation_plan=remediation_plan,
            investigation_duration_ms=round(duration, 2),
        )

    def _deduce_primary_root_cause(
        self,
        candidate_causes: List[Tuple[FailureSignature, Evidence, LogEntry]],
        all_entries: List[LogEntry],
    ) -> Tuple[Optional[FailureSignature], Optional[Evidence], float]:
        """Scores candidate causes by root-cause weight, temporal precedence, and evidence fidelity."""
        if not candidate_causes:
            # Check if there are generic errors or stack traces without named signatures
            for entry in all_entries:
                if entry.level in (LogLevel.ERROR, LogLevel.FATAL) or entry.stack_trace:
                    generic_sig = FailureSignature(
                        signature_id="SIG_GENERIC_ERROR",
                        category="APPLICATION_ERROR",
                        title="Application Unhandled Error",
                        severity=Severity.HIGH,
                        patterns=[],
                        root_cause_weight=50,
                        description="Unhandled application error logged at ERROR or FATAL level.",
                        immediate_action="Inspect the error message and container logs.",
                    )
                    ev = Evidence(
                        line_numbers=[entry.line_number],
                        timestamp=entry.timestamp_str,
                        log_snippet=entry.stack_trace or entry.raw_text,
                        relevance_explanation="First logged critical error line in stream.",
                        pattern_matched="Generic Application Error",
                        confidence=0.75,
                    )
                    return generic_sig, ev, 0.75

            return None, None, 0.0

        # Score candidates:
        # Score = root_cause_weight (0-100)
        #         + temporal bonus (up to +15 for earlier appearance)
        #         + stack trace bonus (+10)
        scored_candidates: List[Tuple[float, FailureSignature, Evidence]] = []
        total_candidates = len(candidate_causes)

        for idx, (sig, ev, entry) in enumerate(candidate_causes):
            base_score = float(sig.root_cause_weight)
            # Earlier events are more likely triggers
            temporal_bonus = 15.0 * (1.0 - (idx / max(total_candidates, 1)))
            stack_bonus = 10.0 if entry.stack_trace else 0.0

            total_score = base_score + temporal_bonus + stack_bonus
            scored_candidates.append((total_score, sig, ev))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_sig, best_ev = scored_candidates[0]

        # Calculate confidence between 0.75 and 0.98
        confidence = min(0.98, max(0.75, (best_score / 125.0)))
        return best_sig, best_ev, round(confidence, 2)

    def _build_timeline(
        self,
        candidate_causes: List[Tuple[FailureSignature, Evidence, LogEntry]],
        all_entries: List[LogEntry],
        primary_sig: Optional[FailureSignature],
    ) -> List[TimelineEvent]:
        """Constructs a chronological narrative of significant events leading to failure."""
        events: List[TimelineEvent] = []
        seen_lines = set()

        # Gather critical entries
        candidates_map = {entry.line_number: (sig, ev) for sig, ev, entry in candidate_causes}

        for entry in all_entries:
            if entry.line_number in seen_lines:
                continue

            is_candidate = entry.line_number in candidates_map
            is_error = entry.level in (LogLevel.ERROR, LogLevel.FATAL, LogLevel.CRITICAL)
            is_warn = entry.level in (LogLevel.WARN, LogLevel.WARNING)

            if is_candidate or is_error or is_warn:
                sig, _ = candidates_map.get(entry.line_number, (None, None))

                # Determine phase
                if sig and primary_sig and sig.signature_id == primary_sig.signature_id and not events:
                    phase = "Trigger / Inception"
                elif not events and is_error:
                    phase = "Initial Anomaly"
                elif sig and sig.category in ("CRASH_LOOP", "PROBE_FAILURE"):
                    phase = "Cascading Impact"
                elif "restarting" in entry.raw_text.lower() or "terminated" in entry.raw_text.lower():
                    phase = "Kubelet Intervention"
                else:
                    phase = "Failure Progression"

                severity = sig.severity if sig else (Severity.HIGH if is_error else Severity.MEDIUM)
                desc = sig.title if sig else entry.message[:120]

                events.append(
                    TimelineEvent(
                        timestamp=entry.timestamp_str or (entry.timestamp.isoformat() if entry.timestamp else f"Line {entry.line_number}"),
                        line_number=entry.line_number,
                        severity=severity,
                        phase=phase,
                        description=desc,
                        component=entry.component,
                        raw_snippet=entry.raw_text[:160],
                    )
                )
                seen_lines.add(entry.line_number)

            if len(events) >= 12:  # Keep timeline concise and impactful
                break

        return events

    def _generate_remediations(
        self,
        primary_sig: Optional[FailureSignature],
        signals: Dict[str, InvestigationSignal],
        primary_pod: Optional[str] = None,
    ) -> List[RemediationStep]:
        """Produces tailored, executable remediation instructions and kubectl commands."""
        import re

        clean_pod = None
        inferred_deploy = None
        if primary_pod:
            clean_pod = primary_pod.replace("pod/", "").strip()
            # If pod has ReplicaSet and Pod hash suffixes e.g. worker-7b56f8f-x9kz -> worker
            if re.search(r"-[a-f0-9]{6,10}-[a-z0-9]{4,6}$", clean_pod):
                inferred_deploy = re.sub(r"-[a-f0-9]{6,10}-[a-z0-9]{4,6}$", "", clean_pod)
            elif "-" in clean_pod:
                inferred_deploy = clean_pod.rsplit("-", 1)[0]
            else:
                inferred_deploy = clean_pod

        steps: List[RemediationStep] = []

        def _substitute(cmd: Optional[str]) -> Optional[str]:
            if not cmd:
                return None
            res = cmd
            if clean_pod:
                res = res.replace("<pod-name>", clean_pod)
            if inferred_deploy:
                res = res.replace("<deployment-name>", inferred_deploy)
            return res

        if primary_sig:
            # Immediate Mitigation
            steps.append(
                RemediationStep(
                    phase="Phase 1: Immediate Mitigation",
                    action=primary_sig.immediate_action,
                    kubectl_command=_substitute(primary_sig.suggested_kubectl),
                    details=f"Address immediate availability disruption caused by {primary_sig.title}.",
                )
            )

            # Specific Root Cause Fixes
            if primary_sig.category == "OOM_KILL":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Increase memory limits and inspect heap allocation in container spec.",
                        kubectl_command=_substitute("kubectl set resources deployment/<deployment-name> --limits=memory=2Gi --requests=memory=1Gi"),
                        details="Configure container memory limits above maximum observed spike threshold to avoid Linux cgroup kill.",
                    )
                )
            elif primary_sig.category == "CONFIG_ERROR":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Create or rectify the missing ConfigMap / Secret and verify key names.",
                        kubectl_command=_substitute("kubectl create configmap <name> --from-literal=<key>=<value>\nkubectl rollout restart deployment/<deployment-name>"),
                        details="Ensure referenced config keys match pod specification exact spelling and namespace.",
                    )
                )
            elif primary_sig.category == "DATABASE_OUTAGE":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Restore database connectivity and verify connection pool boundaries.",
                        kubectl_command=_substitute("kubectl get statefulset,svc -l app=database\nkubectl exec -it <pod-name> -- nc -zv <db-host> <port>"),
                        details="Confirm database port is reachable from worker nodes and database has not reached max_connections.",
                    )
                )
            elif primary_sig.category == "IMAGE_PULL":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Fix container image repository/tag and attach imagePullSecrets if private.",
                        kubectl_command=_substitute("kubectl set image deployment/<deployment-name> <container-name>=<valid-image>:<tag>\nkubectl create secret docker-registry regcred ..."),
                        details="Verify Docker registry permissions and confirm the image tag exists on the remote repository.",
                    )
                )
            elif primary_sig.category == "RBAC_PERMISSION":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Grant required RBAC verb/resource permissions to the Pod's ServiceAccount.",
                        kubectl_command=_substitute("kubectl create role <role-name> --verb=get,list,watch --resource=pods\nkubectl create rolebinding <binding-name> --role=<role-name> --serviceaccount=<ns>:<sa-name>"),
                        details="Validate updated permissions with `kubectl auth can-i` using the service account impersonation.",
                    )
                )
            elif primary_sig.category == "NETWORK_DNS":
                steps.append(
                    RemediationStep(
                        phase="Phase 2: Root Cause Fix",
                        action="Inspect CoreDNS health and verify internal service domain naming.",
                        kubectl_command=_substitute("kubectl rollout restart deployment coredns -n kube-system\nkubectl get ep <target-service>"),
                        details="Ensure the service has active ready endpoints and uses the standard cluster domain suffix.",
                    )
                )

            # Long Term Prevention
            if primary_sig.prevention_tip:
                steps.append(
                    RemediationStep(
                        phase="Phase 3: Long-Term Prevention",
                        action="Implement systemic safeguards and monitoring.",
                        kubectl_command=None,
                        details=primary_sig.prevention_tip,
                    )
                )

        # Generic best-practice step if nothing specific
        if not steps:
            steps.append(
                RemediationStep(
                    phase="Phase 1: Investigation",
                    action="Check recent container termination state and previous pod logs.",
                    kubectl_command="kubectl logs <pod-name> --previous\nkubectl describe pod <pod-name>",
                    details="Review previous container termination reason, exit code, and recent events.",
                )
            )

        return steps

    def _formulate_summary(
        self,
        primary_sig: Optional[FailureSignature],
        primary_evidence: Optional[Evidence],
        signals: Dict[str, InvestigationSignal],
        error_count: int,
    ) -> str:
        """Constructs an executive incident summary."""
        if primary_sig:
            ev_loc = f" (first isolated at line {primary_evidence.line_numbers[0]})" if primary_evidence else ""
            summary = (
                f"The investigation identified '{primary_sig.title}' as the primary root cause{ev_loc}. "
                f"{primary_sig.description} "
            )
            # Mention secondary symptoms
            secondary_symptoms = [s.title for s in signals.values() if s.signal_id != primary_sig.signature_id]
            if secondary_symptoms:
                summary += f"This triggered secondary cascading symptoms including: {', '.join(secondary_symptoms[:3])}. "
            summary += f"A total of {error_count} error-level log entries were recorded during the incident period."
            return summary
        else:
            return (
                f"Log scan completed with {error_count} errors detected. No single critical Kubernetes signature "
                f"dominated the log stream. Review the detailed timeline and error lines for individual stack traces."
            )

    def _formulate_detailed_findings(
        self,
        primary_sig: Optional[FailureSignature],
        signals: Dict[str, InvestigationSignal],
        error_count: int,
        warning_count: int,
    ) -> List[str]:
        """Compiles bulleted findings for technical review."""
        findings: List[str] = []
        if primary_sig:
            findings.append(f"**Root Cause**: {primary_sig.title} (Category: `{primary_sig.category}`).")
            findings.append(f"**Root Cause Impact**: {primary_sig.description}")

        for sig in signals.values():
            findings.append(
                f"**Observed Signal [{sig.severity.value}]**: {sig.title} — occurred {sig.occurrence_count} time(s) "
                f"across component(s): `{sig.impact_scope or 'default'}`. First detected at `{sig.first_seen or 'early log'}`."
            )

        findings.append(f"**Log Volume Analysis**: Analyzed stream contained {error_count} error events and {warning_count} warning events.")
        return findings
