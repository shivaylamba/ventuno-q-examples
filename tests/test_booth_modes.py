import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'ai-object-story-booth/python'))
from story import MODES, build_prompt, knob_delta

class EncoderModes(unittest.TestCase):
    def test_encoder_wrap_does_not_jump_modes(self):
        self.assertEqual(knob_delta(-32768, 32767), 1)
        self.assertEqual(knob_delta(32767, -32768), -1)
        self.assertEqual(knob_delta(-2, -5), 3)
        self.assertEqual(knob_delta(42, 42), 0)

    def test_every_mode_has_its_own_prompt(self):
        prompts = [build_prompt(mode['id']) for mode in MODES]
        self.assertEqual(len(set(prompts)), 3)
        with self.assertRaises(ValueError):
            build_prompt('unsupported')

if __name__ == '__main__':
    unittest.main()
