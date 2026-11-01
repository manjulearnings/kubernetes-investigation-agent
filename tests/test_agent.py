import unittest
from pathlib import Path
from k8s_agent.agent import KubernetesInvestigationAgent
from k8s_agent.models import Severity


class TestKubernetesInvestigationAgent(unittest.TestCase):
    def setUp(self):
        self.agent = KubernetesInvestigationAgent()
        self.sample_dir = Path(__file__).resolve().parent.parent / "sample_logs"

    def test_investigate_oom_file(self):
        oom_file = self.sample_dir / "01_crashloop_oom.log"
        report = self.agent.investigate_file(oom_file)

        self.assertEqual(report.source_name, "01_crashloop_oom.log")
        self.assertEqual(report.root_cause_category, "OOM_KILL")
        self.assertEqual(report.severity, Severity.CRITICAL)
        self.assertTrue(len(report.key_evidence) > 0)
        self.assertTrue(len(report.timeline) > 0)
        self.assertTrue(len(report.remediation_plan) > 0)

        # Verify markdown rendering
        md = self.agent.to_markdown(report)
        self.assertIn("# 🛡️ Kubernetes Incident Investigation Report", md)
        self.assertIn("Supporting Log Evidence", md)

        # Verify JSON export
        json_str = self.agent.to_json(report)
        self.assertIn('"root_cause_category": "OOM_KILL"', json_str)

    def test_investigate_db_outage_file(self):
        db_file = self.sample_dir / "02_db_connection_refused.log"
        report = self.agent.investigate_file(db_file)

        self.assertEqual(report.root_cause_category, "DATABASE_OUTAGE")
        self.assertEqual(report.severity, Severity.HIGH)

    def test_investigate_config_and_dns_file(self):
        cfg_file = self.sample_dir / "03_dns_and_config_missing.log"
        report = self.agent.investigate_file(cfg_file)

        self.assertEqual(report.root_cause_category, "CONFIG_ERROR")
        self.assertIn("Missing ConfigMap", report.primary_root_cause)

    def test_investigate_rbac_file(self):
        rbac_file = self.sample_dir / "04_rbac_permission_denied.log"
        report = self.agent.investigate_file(rbac_file)

        self.assertEqual(report.root_cause_category, "RBAC_PERMISSION")

    def test_investigate_tls_file(self):
        tls_file = self.sample_dir / "05_tls_cert_expired.log"
        report = self.agent.investigate_file(tls_file)

        self.assertEqual(report.root_cause_category, "TLS_ERROR")


if __name__ == "__main__":
    unittest.main()
