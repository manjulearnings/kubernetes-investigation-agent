import unittest
from k8s_agent.parser import KubernetesLogParser
from k8s_agent.models import LogLevel


class TestKubernetesLogParser(unittest.TestCase):
    def setUp(self):
        self.parser = KubernetesLogParser()

    def test_parse_cri_format(self):
        raw = "2026-11-01T10:15:00.100Z stdout F [INFO] Application started successfully"
        entries = self.parser.parse_text(raw)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.line_number, 1)
        self.assertEqual(entry.stream, "stdout")
        self.assertEqual(entry.level, LogLevel.INFO)
        self.assertIn("Application started successfully", entry.message)
        self.assertIsNotNone(entry.timestamp)

    def test_parse_json_format(self):
        raw = '{"timestamp":"2026-11-01T11:01:22Z","level":"error","component":"orders-api","message":"psycopg2.OperationalError: could not connect to server"}'
        entries = self.parser.parse_text(raw)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.level, LogLevel.ERROR)
        self.assertEqual(entry.component, "orders-api")
        self.assertIn("psycopg2.OperationalError", entry.message)

    def test_parse_k8s_event_format(self):
        raw = "10s  Warning  BackOff  pod/auth-svc-1  Back-off 10s restarting failed container"
        entries = self.parser.parse_text(raw)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.level, LogLevel.WARN)
        self.assertEqual(entry.component, "pod/auth-svc-1")
        self.assertIn("Back-off 10s restarting", entry.message)

    def test_parse_multiline_stack_trace(self):
        raw = """2026-11-01T10:16:02.120Z stderr F java.lang.OutOfMemoryError: Java heap space
2026-11-01T10:16:02.122Z stderr F 	at java.base/java.util.Arrays.copyOf(Arrays.java:3537)
2026-11-01T10:16:02.125Z stderr F 	at com.example.processor.TransactionBatch.loadAll(TransactionBatch.java:142)
2026-11-01T10:16:03.010Z stderr F [FATAL] Command terminated with exit code 137"""
        entries = self.parser.parse_text(raw)
        # Entry 1 should contain the Java stack trace
        first_entry = entries[0]
        self.assertTrue(first_entry.is_multiline or first_entry.stack_trace is not None)
        self.assertIn("java.lang.OutOfMemoryError", first_entry.raw_text)


if __name__ == "__main__":
    unittest.main()
