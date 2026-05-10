import unittest

from backend.ai_analyzer import analyze_params


class AiAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_without_api_key(self):
        result = await analyze_params(
            code="lr = 0.001\n",
            params=[{
                "id": "param_1",
                "name": "lr",
                "value": 0.001,
                "originalText": "0.001",
                "type": "float",
                "line": 1,
                "col": 5,
                "endLine": 1,
                "endCol": 10,
                "source": "assign",
                "group": "训练参数",
            }],
        )

        self.assertTrue(result["fallback"])
        self.assertEqual(result["params"][0]["name"], "lr")
        self.assertTrue(result["sections"])


if __name__ == "__main__":
    unittest.main()
