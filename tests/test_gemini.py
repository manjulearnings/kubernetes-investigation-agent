import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from k8s_agent.agent import KubernetesInvestigationAgent


class TestGeminiInvestigation(unittest.TestCase):
    def setUp(self):
        self.sample_dir = Path(__file__).resolve().parent.parent / "sample_logs"
        self.custom_error_log = self.sample_dir / "06_custom_payment_stripe_error.log"

    def test_unclassified_error_without_api_key(self):
        # Without an API key, agent falls back gracefully to deterministic rule engine & helpful AI tip
        agent = KubernetesInvestigationAgent()
        report = agent.investigate_file(self.custom_error_log)

        self.assertEqual(report.root_cause_category, "APPLICATION_PANIC")
        self.assertTrue(any("AI Tip" in finding for finding in report.detailed_findings))

    @patch("k8s_agent.gemini.httpx.Client")
    def test_unclassified_error_with_mocked_gemini(self, mock_client_cls):
        # Mock Gemini response to verify full diagnosis injection
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_gemini_json = {
            "root_cause_title": "Stripe API Key Authentication Failure",
            "category": "PAYMENT_AUTH_ERROR",
            "confidence_score": 0.95,
            "executive_summary": "The checkout worker crashed because STRIPE_API_KEY was not configured in the pod environment.",
            "remediation_plan": [
                {
                    "phase": "Phase 1: Immediate Mitigation",
                    "action": "Inject Stripe API key secret into the deployment.",
                    "kubectl_command": "kubectl set env deployment/payment-svc --from=secret/stripe-secret",
                    "details": "Ensures process can authenticate with Stripe."
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        import json
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps(mock_gemini_json)}
                        ]
                    }
                }
            ]
        }
        mock_client.post.return_value = mock_resp

        # Run agent with a dummy API key
        agent = KubernetesInvestigationAgent(gemini_api_key="mock_key_12345")
        report = agent.investigate_file(self.custom_error_log)

        # Check Gemini's output was injected
        self.assertIn("Stripe API Key Authentication Failure", report.primary_root_cause)
        self.assertEqual(report.root_cause_category, "PAYMENT_AUTH_ERROR")
        self.assertEqual(report.confidence_score, 0.95)
        self.assertIn("Gemini AI SRE Diagnosis", report.executive_summary)
        self.assertTrue(len(report.remediation_plan) > 0)
        self.assertIn("kubectl set env deployment/payment-svc", report.remediation_plan[0].kubectl_command)

    def test_default_model_is_modern(self):
        # Verify default model is gemini-3.8-flash
        from k8s_agent.gemini import GeminiInvestigator
        investigator = GeminiInvestigator()
        self.assertEqual(investigator.model, "gemini-3.8-flash")

    @patch("k8s_agent.gemini.httpx.Client")
    def test_latest_model_auto_discovery(self, mock_client_cls):
        # Verify 'latest' dynamically resolves via Google API
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "models/gemini-3-flash"},
                {"name": "models/gemini-3.8-flash"},
            ]
        }
        mock_client.get.return_value = mock_resp

        from k8s_agent.gemini import GeminiInvestigator
        investigator = GeminiInvestigator(api_key="test-key", model="latest")
        self.assertEqual(investigator.model, "gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main()
