import unittest
import asyncio
from agents.base import escape_applescript_string
from agents.system_agent import SystemAgent

class TestSecurity(unittest.TestCase):
    def test_escape_applescript_string(self):
        cases = [
            ('hello', 'hello'),
            ('hello "world"', 'hello \\"world\\"'),
            ('back\\slash', 'back\\\\slash'),
            ('quote " and back\\slash', 'quote \\" and back\\\\slash'),
            ('"', '\\"'),
            ('\\', '\\\\'),
            ('', ''),
        ]
        for input_str, expected in cases:
            self.assertEqual(escape_applescript_string(input_str), expected)

class TestSystemAgentSecurity(unittest.IsolatedAsyncioTestCase):
    async def test_tool_say_injection(self):
        agent = SystemAgent()
        captured_scripts = []
        async def mock_run_osascript(script):
            captured_scripts.append(script)
            return "mock_result"
        agent._run_osascript = mock_run_osascript

        malicious_text = 'hello" & (do shell script "whoami") & "'
        await agent._tool_say(malicious_text)

        expected_script = 'say "hello\\" & (do shell script \\"whoami\\") & \\""'
        self.assertEqual(captured_scripts[0], expected_script)

    async def test_tool_open_app_injection(self):
        agent = SystemAgent()
        captured_scripts = []
        async def mock_run_osascript(script):
            captured_scripts.append(script)
            return "mock_result"
        agent._run_osascript = mock_run_osascript

        malicious_app = 'Safari" to activate\ndo shell script "whoami"\n--'
        await agent._tool_open_app(malicious_app)

        script = captured_scripts[0]
        self.assertIn('tell application "Safari\\" to activate', script)
        self.assertIn('do shell script \\"whoami\\"', script)
        self.assertIn('process "Safari\\" to activate', script)

if __name__ == '__main__':
    unittest.main()
