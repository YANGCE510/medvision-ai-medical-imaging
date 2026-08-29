from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from core.ai_trace import AiTraceStore, normalize_trace_id  # noqa: E402


class AiTraceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = AiTraceStore(Path(self.temporary_directory.name))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_sensitive_trace_metadata_is_redacted(self) -> None:
        trace_id = self.store.start(
            "tr_privacy_check_001",
            "rag_query",
            actor_user_id=7,
            metadata={
                "question": "患者原始问题不应写入 trace",
                "answer": "模型原始回答不应写入 trace",
                "patient_name": "测试姓名",
                "question_fingerprint": {"length": 12, "sha256_prefix": "abc123"},
                "model": "ppgl-qwen3-8b-q4:latest",
            },
        )

        trace = self.store.get(trace_id, actor_user_id=7)

        self.assertIsNotNone(trace)
        self.assertEqual(trace["metadata"]["question"], "[redacted]")
        self.assertEqual(trace["metadata"]["answer"], "[redacted]")
        self.assertEqual(trace["metadata"]["patient_name"], "[redacted]")
        self.assertEqual(trace["metadata"]["question_fingerprint"]["sha256_prefix"], "abc123")
        self.assertEqual(trace["metadata"]["model"], "ppgl-qwen3-8b-q4:latest")

    def test_trace_access_is_scoped_to_the_requesting_user(self) -> None:
        own_trace = self.store.start("tr_owner_001", "rag_query", actor_user_id=11)
        other_trace = self.store.start("tr_owner_002", "rag_query", actor_user_id=22)

        visible_to_first_user = self.store.list(actor_user_id=11)

        self.assertEqual([item["trace_id"] for item in visible_to_first_user], [own_trace])
        self.assertIsNone(self.store.get(other_trace, actor_user_id=11))
        self.assertIsNotNone(self.store.get(other_trace, actor_user_id=11, is_admin=True))

    def test_completed_trace_contains_stage_and_result_summary(self) -> None:
        trace_id = self.store.start("tr_lifecycle_001", "ppgl_segmentation", actor_user_id=3)
        self.store.event(
            trace_id,
            "gpu_admission",
            "completed",
            duration_ms=37.5,
            details={"queue_wait_seconds": 0},
        )
        self.store.finish(
            trace_id,
            "completed",
            duration_ms=1234.5,
            result={"task": "PPGL 肿瘤分割", "model": "PPGL 分割权重"},
        )

        trace = self.store.get(trace_id, actor_user_id=3)

        self.assertEqual(trace["status"], "completed")
        self.assertEqual(trace["duration_ms"], 1234.5)
        self.assertEqual(trace["result"]["task"], "PPGL 肿瘤分割")
        self.assertIn("gpu_admission", [item["stage"] for item in trace["events"]])

    def test_invalid_trace_identifier_is_replaced(self) -> None:
        normalized = normalize_trace_id("../../private-trace")

        self.assertTrue(normalized.startswith("tr_"))
        self.assertNotIn("/", normalized)


if __name__ == "__main__":
    unittest.main()
