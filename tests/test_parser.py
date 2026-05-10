import unittest

from backend.parser import parse_code


class ParserTests(unittest.TestCase):
    def test_extracts_common_training_params(self):
        result = parse_code("lr = 0.001\nepochs = 10\nprint(lr)\n")
        self.assertEqual(result["errors"], [])

        names = {param["name"] for param in result["params"]}
        self.assertIn("lr", names)
        self.assertIn("epochs", names)

    def test_reports_syntax_errors_without_crashing(self):
        result = parse_code("def broken(:\n")
        self.assertEqual(result["params"], [])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
