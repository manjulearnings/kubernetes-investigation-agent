import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class LogEntry(BaseModel):
    """Represents a single parsed log line or multiline block from Kubernetes."""
    line_number: int
    raw_text: str
    message: str
    timestamp: Optional[datetime.datetime] = None
    timestamp_str: Optional[str] = None
    level: LogLevel = LogLevel.UNKNOWN
    component: Optional[str] = None  # Pod, container, or service name
    stream: Optional[str] = None     # stdout, stderr
    is_multiline: bool = False
    stack_trace: Optional[str] = None


class Evidence(BaseModel):
    """Exact log evidence supporting a finding or diagnosis."""
    line_numbers: List[int]
    timestamp: Optional[str] = None
    log_snippet: str
    relevance_explanation: str
    pattern_matched: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class InvestigationSignal(BaseModel):
    """A detected anomaly, error pattern, or symptom in the logs."""
    signal_id: str
    category: str
    title: str
    severity: Severity
    description: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    occurrence_count: int = 1
    evidences: List[Evidence] = Field(default_factory=list)
    impact_scope: Optional[str] = None


class TimelineEvent(BaseModel):
    """A chronological event in the failure sequence."""
    timestamp: Optional[str] = None
    line_number: int
    severity: Severity
    phase: str
    description: str
    component: Optional[str] = None
    raw_snippet: str


class RemediationStep(BaseModel):
    """Actionable remediation recommendation."""
    phase: str  # e.g., "Immediate Mitigation", "Root Cause Fix", "Prevention"
    action: str
    kubectl_command: Optional[str] = None
    details: str


class InvestigationReport(BaseModel):
    """Full investigation report detailing root cause, timeline, and supporting evidence."""
    incident_id: str
    timestamp: str
    source_name: str
    total_lines_analyzed: int
    error_count: int
    warning_count: int
    severity: Severity
    primary_root_cause: str
    root_cause_category: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    executive_summary: str
    detailed_findings: List[str] = Field(default_factory=list)
    signals: List[InvestigationSignal] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    key_evidence: List[Evidence] = Field(default_factory=list)
    remediation_plan: List[RemediationStep] = Field(default_factory=list)
    investigation_duration_ms: float = 0.0
    agent_version: str = "1.0.0"
