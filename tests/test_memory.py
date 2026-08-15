import os
import tempfile
import unittest
from unittest.mock import patch

import core.memory as ai_memory


class MemoryTests(unittest.TestCase):
    def test_extract_name(self):
        self.assertEqual(ai_memory.extract_facts("my name is alice"),
                         [("name", "alice")])

    def test_extract_interest(self):
        facts = ai_memory.extract_facts("i like football")
        self.assertIn(("interests", "football"), facts)

    def test_extract_multiple_interests(self):
        facts = ai_memory.extract_facts("i like football and chess")
        self.assertIn(("interests", "football"), facts)
        self.assertIn(("interests", "chess"), facts)

    def test_extract_favorite(self):
        facts = ai_memory.extract_facts("my favourite colour is blue")
        self.assertIn(("favorite_color", "blue"), facts)

    def test_extract_location(self):
        facts = ai_memory.extract_facts("i live in new york")
        self.assertIn(("location", "new york"), facts)

    def test_ignore_stopword_interests(self):
        self.assertNotIn(("interests", "you"),
                         ai_memory.extract_facts("i love you"))

    def test_name_stops_at_new_clause(self):
        """'my name is sam and I like chess' must store name='sam', not
        the whole trailing clause."""
        facts = ai_memory.extract_facts("my name is sam and I like chess")
        self.assertIn(("name", "sam"), facts)
        self.assertIn(("interests", "chess"), facts)
        self.assertNotIn(("name", "sam and i like chess"), facts)

    def test_favorite_stops_at_new_clause(self):
        facts = ai_memory.extract_facts(
            "my favourite colour is blue and my name is sam")
        self.assertIn(("favorite_color", "blue"), facts)
        self.assertIn(("name", "sam"), facts)

    def test_location_stops_at_new_clause(self):
        facts = ai_memory.extract_facts(
            "i live in new york and i like pizza")
        self.assertIn(("location", "new york"), facts)
        self.assertIn(("interests", "pizza"), facts)

    def test_multi_word_name_kept(self):
        self.assertIn(("name", "john smith"),
                      ai_memory.extract_facts("call me john smith"))

    def test_apply_merges_and_dedupes(self):
        mem = {"name": "alice"}
        changed = ai_memory.apply_facts(mem, [("interests", "chess")])
        self.assertEqual(changed, [("interests", "chess")])
        changed2 = ai_memory.apply_facts(mem, [("interests", "chess")])
        self.assertEqual(changed2, [])  # already known

    def test_apply_updates_single_values(self):
        mem = {"name": "alice"}
        ai_memory.apply_facts(mem, [("name", "bob")])
        self.assertEqual(mem["name"], "bob")

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "memory.json")
            with patch.object(ai_memory, "MEMORY_FILE", path):
                ai_memory.save_memory({"name": "bob", "interests": ["chess"]})
                self.assertEqual(ai_memory.load_memory(),
                                 {"name": "bob", "interests": ["chess"]})

    def test_clear_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "memory.json")
            with patch.object(ai_memory, "MEMORY_FILE", path):
                ai_memory.save_memory({"name": "bob"})
                self.assertTrue(ai_memory.clear_memory())
                self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
