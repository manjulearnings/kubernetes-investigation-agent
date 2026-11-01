import unittest
from k8s_agent.parser import KubernetesLogParser
from k8s_agent.engine import InvestigationEngine
from k8s_agent.models import Severity


class TestInvestigationEngine(unittest.TestCase):
    def setUp(self):
        self.parser = KubernetesLogParser()
        self.engine = InvestigationEngine()

    def test_oom_prioritized_over_crashloop(self):
        log_content = """2026-11-01T10:16:02.120Z stderr F java.lang.OutOfMemoryError: Java heap space
2026-11-01T10:16:03.010Z stderr F [FATAL] Kernel cgroup out of memory: Killed process 42 exit code 137
2026-11-01T10:16:20.000Z stdout F Warning BackOff pod/trans-1 Back-off restarting failed container
2026-11-01T10:17:00.000Z stdout F Warning BackOff pod/trans-1 CrashLoopBackOff"""
        entries = self.parser.parse_text(log_content)
        report = self.engine.analyze(entries)

        self.assertEqual(report.severity, Severity.CRITICAL)
        self.assertEqual(report.root_cause_category, "OOM_KILL")
        self.assertIn("Out of Memory", report.primary_root_cause)
        self.assertGreater(report.confidence_score, 0.80)
        self.assertTrue(len(report.key_evidence) > 0)
        # Check evidence points to line 1 or 2
        ev_lines = [l for ev in report.key_evidence for l in ev.line_numbers]
        self.assertTrue(1 in ev_lines or 2 in ev_lines)

    def test_database_outage_prioritized_over_readiness_probe(self):
        log_content = """{"timestamp":"2026-11-01T11:01:22Z","level":"error","component":"orders-api","message":"psycopg2.OperationalError: could not connect to server: Connection refused"}
{"timestamp":"2026-11-01T11:01:30Z","level":"warn","component":"kubelet","message":"Readiness probe failed: HTTP probe failed with statuscode: 500"}
{"timestamp":"2026-11-01T11:01:40Z","level":"error","component":"ingress-nginx","message":"502 Bad Gateway while connecting to upstream service"}"""
        entries = self.parser.parse_text(log_content)
        report = self.engine.analyze(entries)

        self.assertEqual(report.root_cause_category, "DATABASE_OUTAGE")
        self.assertIn("Database", report.primary_root_cause)
        # Check remediation includes database checks
        remediations = [r.action for r in report.remediation_plan]
        self.assertTrue(any("database" in r.lower() for r in remediations))


if __name__ == "__main__":
    unittest.main()
