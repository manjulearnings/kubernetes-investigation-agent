import re
import json
from datetime import datetime
from typing import List, Optional
from .models import LogEntry, LogLevel


# Regex for CRI format: 2026-11-01T08:14:22.123456789Z stdout F [INFO] ...
# Using \s[FP]\s? to preserve leading message indentation (like tabs in stack traces)
CRI_REGEX = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+(?P<stream>stdout|stderr)\s+[FP]\s?(?P<message>.*)$"
)

# Regex for Klog format: E1101 08:14:22.123456 1 reflector.go:140] Failed to watch...
KLOG_REGEX = re.compile(
    r"^(?P<level>[IWEF])(?P<month>\d{2})(?P<day>\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\d+\s+(?P<file>[^:]+:\d+)\]\s+(?P<message>.*)$"
)

# Regex for Kubectl logs prefix: pod/name [container] timestamp level message or [container] message
KUBECTL_PREFIX_REGEX = re.compile(
    r"^(?:(?:pod/)?(?P<pod>[a-zA-Z0-9_\-\.]+)\s+)?(?:\[(?P<container>[a-zA-Z0-9_\-\.]+)\]\s+)?(?P<rest>.*)$"
)

# Regex for ISO-like timestamp at beginning of line
TIMESTAMP_REGEX = re.compile(
    r"^(?:\[)?(?P<ts>\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)(?:\])?\s*(?P<rest>.*)$"
)

# Regex for Log Level detection in line
LEVEL_REGEX = re.compile(
    r"\b(?P<level>FATAL|CRITICAL|SEVERE|ERROR|WARN|WARNING|INFO|DEBUG|TRACE)\b",
    re.IGNORECASE
)

# Regex for Stack trace start & continuation
STACK_TRACE_START = re.compile(
    r"(Traceback \(most recent call last\):|"
    r"Exception in thread \".*\"|"
    r"panic: runtime error:|"
    r"fatal error:|"
    r"\b[a-zA-Z0-9_.]*(?:Exception|Error):|"
    r"goroutine \d+ \[running\]:)",
    re.IGNORECASE
)

STACK_TRACE_LINE = re.compile(
    r"^(\s*at\s+[\w\$./]+|"  # Java
    r"\s*File\s+\".*\",\s+line\s+\d+|"  # Python
    r"\s*Caused by:|"  # Java
    r"\s*[\w\./\-]+:\d+\s+\+0x[0-9a-f]+|"  # Go
    r"\s*\.{3}\s+\d+\s+more)",  # Java
    re.IGNORECASE
)

# Kubernetes Event format: 2m  Warning  BackOff  pod/auth-svc  Back-off restarting
K8S_EVENT_REGEX = re.compile(
    r"^(?P<age>[\dsmh]+)\s+(?P<type>Normal|Warning|Error)\s+(?P<reason>[a-zA-Z0-9_\-]+)\s+(?P<object>[a-zA-Z0-9_\-\./]+)\s+(?P<message>.*)$"
)


class KubernetesLogParser:
    """Intelligent parser for multi-format Kubernetes logs, events, and stack traces."""

    def __init__(self):
        pass

    def parse_text(self, log_content: str) -> List[LogEntry]:
        """Parses a multi-line string of log data into structured LogEntry objects."""
        lines = log_content.splitlines()
        entries: List[LogEntry] = []
        current_entry: Optional[LogEntry] = None
        in_stack_trace = False
        stack_trace_lines: List[str] = []

        for line_idx, raw_line in enumerate(lines, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            # Strip CRI prefix or pod prefix if present to check the actual log payload
            payload = self._extract_payload_message(raw_line)

            # Check if this line is part of a continuing stack trace
            if in_stack_trace and (STACK_TRACE_LINE.search(payload) or raw_line.startswith("  ") or payload.startswith(" ")):
                stack_trace_lines.append(raw_line)
                if current_entry:
                    current_entry.is_multiline = True
                    current_entry.stack_trace = "\n".join(stack_trace_lines)
                continue
            elif in_stack_trace:
                # End of stack trace
                in_stack_trace = False
                stack_trace_lines = []

            # Check if line initiates a stack trace
            is_start = bool(STACK_TRACE_START.search(payload) or STACK_TRACE_START.search(raw_line))
            if is_start:
                in_stack_trace = True
                stack_trace_lines = [raw_line]

            # Parse line as a new LogEntry
            entry = self._parse_single_line(line_idx, raw_line)
            if is_start:
                entry.is_multiline = True
                entry.stack_trace = raw_line

            entries.append(entry)
            current_entry = entry

        return entries

    def _extract_payload_message(self, raw_line: str) -> str:
        """Strips timestamp and container runtime prefixes to inspect the raw message text."""
        stripped = raw_line.strip()
        cri_match = CRI_REGEX.match(stripped)
        if cri_match:
            return cri_match.group("message")
        return stripped

    def _parse_single_line(self, line_num: int, raw_line: str) -> LogEntry:
        """Determines format and extracts fields."""
        stripped = raw_line.strip()

        # 1. Check for JSON format
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict):
                    return self._parse_json_entry(line_num, raw_line, data)
            except Exception:
                pass

        # 2. Check for CRI format (e.g. containerd/CRI-O)
        cri_match = CRI_REGEX.match(stripped)
        if cri_match:
            ts_str = cri_match.group("timestamp")
            stream = cri_match.group("stream")
            msg = cri_match.group("message")
            level = self._detect_level(msg)
            if stream == "stderr" and level == LogLevel.UNKNOWN:
                level = LogLevel.ERROR
            parsed_dt = self._parse_iso_timestamp(ts_str)

            # Check if inner message contains K8s Event or Pod references
            component = None
            ev_match = K8S_EVENT_REGEX.match(msg.strip())
            if ev_match:
                component = ev_match.group("object")
                reason = ev_match.group("reason")
                evt_type = ev_match.group("type")
                level = LogLevel.WARN if evt_type == "Warning" else (LogLevel.ERROR if evt_type == "Error" else LogLevel.INFO)
                msg = f"[{reason}] on {component}: {ev_match.group('message')}"
            else:
                pod_m = re.search(r"\b(?:pod/|in pod\s+)([a-zA-Z0-9_\-\.]+)", msg)
                if pod_m:
                    component = f"pod/{pod_m.group(1)}"

            return LogEntry(
                line_number=line_num,
                raw_text=raw_line,
                message=msg,
                timestamp=parsed_dt,
                timestamp_str=ts_str,
                level=level,
                stream=stream,
                component=component,
            )

        # 3. Check for K8s Event format
        event_match = K8S_EVENT_REGEX.match(stripped)
        if event_match:
            evt_type = event_match.group("type")
            reason = event_match.group("reason")
            obj = event_match.group("object")
            msg = event_match.group("message")
            level = LogLevel.WARN if evt_type == "Warning" else (LogLevel.ERROR if evt_type == "Error" else LogLevel.INFO)
            full_msg = f"[{reason}] on {obj}: {msg}"
            return LogEntry(
                line_number=line_num,
                raw_text=raw_line,
                message=full_msg,
                level=level,
                component=obj,
            )

        # 4. Check for Klog format (I0512 12:34:56.789012 ...)
        klog_match = KLOG_REGEX.match(stripped)
        if klog_match:
            klevel_char = klog_match.group("level")
            klevel_map = {
                "I": LogLevel.INFO,
                "W": LogLevel.WARN,
                "E": LogLevel.ERROR,
                "F": LogLevel.FATAL,
            }
            level = klevel_map.get(klevel_char, LogLevel.UNKNOWN)
            file_loc = klog_match.group("file")
            msg = klog_match.group("message")
            time_str = f"{klog_match.group('month')}-{klog_match.group('day')} {klog_match.group('time')}"
            return LogEntry(
                line_number=line_num,
                raw_text=raw_line,
                message=msg,
                timestamp_str=time_str,
                level=level,
                component=file_loc,
            )

        # 5. Check for Pod / Container prefix (pod/xxx [container] ...)
        prefix_match = KUBECTL_PREFIX_REGEX.match(stripped)
        component = None
        remaining = stripped
        if prefix_match and (prefix_match.group("pod") or prefix_match.group("container")):
            pod = prefix_match.group("pod")
            container = prefix_match.group("container")
            component = f"{pod}/{container}" if (pod and container) else (pod or container)
            remaining = prefix_match.group("rest")

        # Extract timestamp if present in remaining
        ts_match = TIMESTAMP_REGEX.match(remaining)
        timestamp_str = None
        parsed_dt = None
        if ts_match:
            timestamp_str = ts_match.group("ts")
            parsed_dt = self._parse_iso_timestamp(timestamp_str)
            remaining = ts_match.group("rest")

        level = self._detect_level(remaining)

        return LogEntry(
            line_number=line_num,
            raw_text=raw_line,
            message=remaining if remaining else stripped,
            timestamp=parsed_dt,
            timestamp_str=timestamp_str,
            level=level,
            component=component,
        )

    def _parse_json_entry(self, line_num: int, raw_line: str, data: dict) -> LogEntry:
        """Parses structured JSON log entry."""
        ts_str = None
        for key in ["time", "timestamp", "ts", "@timestamp", "date", "datetime"]:
            if key in data and isinstance(data[key], (str, int, float)):
                ts_str = str(data[key])
                break

        level = LogLevel.UNKNOWN
        for key in ["level", "severity", "log_level", "loglevel"]:
            if key in data:
                level_raw = str(data[key]).upper()
                if "WARN" in level_raw:
                    level = LogLevel.WARN
                elif "ERR" in level_raw:
                    level = LogLevel.ERROR
                elif "FATAL" in level_raw or "CRIT" in level_raw:
                    level = LogLevel.FATAL
                elif "INFO" in level_raw:
                    level = LogLevel.INFO
                elif "DEBUG" in level_raw:
                    level = LogLevel.DEBUG
                break

        message = ""
        for key in ["message", "msg", "log", "text", "error", "err"]:
            if key in data and data[key]:
                message = str(data[key])
                break
        if not message:
            message = str(data)

        component = None
        for key in ["component", "pod", "pod_name", "container", "container_name", "service", "app"]:
            if key in data and data[key]:
                component = str(data[key])
                break

        stack_trace = None
        for key in ["stack", "stacktrace", "trace", "exception", "error_stack"]:
            if key in data and data[key]:
                stack_trace = str(data[key])
                break

        parsed_dt = self._parse_iso_timestamp(ts_str) if ts_str else None

        return LogEntry(
            line_number=line_num,
            raw_text=raw_line,
            message=message,
            timestamp=parsed_dt,
            timestamp_str=ts_str,
            level=level,
            component=component,
            is_multiline=bool(stack_trace),
            stack_trace=stack_trace,
        )

    def _detect_level(self, text: str) -> LogLevel:
        """Detects log level from a text string."""
        match = LEVEL_REGEX.search(text)
        if match:
            lvl = match.group("level").upper()
            if lvl in ("WARN", "WARNING"):
                return LogLevel.WARN
            if lvl in ("ERROR", "SEVERE"):
                return LogLevel.ERROR
            if lvl in ("FATAL", "CRITICAL"):
                return LogLevel.FATAL
            if lvl == "INFO":
                return LogLevel.INFO
            if lvl in ("DEBUG", "TRACE"):
                return LogLevel.DEBUG

        lower_text = text.lower()
        if "fatal" in lower_text or "panic:" in lower_text or "oomkilled" in lower_text:
            return LogLevel.FATAL
        if "error" in lower_text or "failed" in lower_text or "exception" in lower_text:
            return LogLevel.ERROR
        if "warning" in lower_text or "warn" in lower_text:
            return LogLevel.WARN

        return LogLevel.UNKNOWN

    def _parse_iso_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        """Attempts to parse standard ISO-8601 or common formats."""
        if not ts_str:
            return None
        cleaned = ts_str.replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
        ):
            try:
                if "." in cleaned:
                    parts = cleaned.split(".")
                    subsecond_and_tz = parts[1]
                    tz_match = re.search(r"([+-]\d{2}:?\d{2})$", subsecond_and_tz)
                    if tz_match:
                        tz_str = tz_match.group(1)
                        sub_digits = subsecond_and_tz[:tz_match.start()]
                        truncated_sub = (sub_digits[:6]).ljust(6, "0")
                        cleaned = f"{parts[0]}.{truncated_sub}{tz_str}"
                    else:
                        truncated_sub = (subsecond_and_tz[:6]).ljust(6, "0")
                        cleaned = f"{parts[0]}.{truncated_sub}"
                return datetime.fromisoformat(cleaned)
            except Exception:
                continue
        return None
