"""Static regression checks for Vietnamese UI and beginner navigation.

Browser rendering still needs a real Windows Cốc Cốc/Chrome review;
these tests guard navigation hooks, fonts and UTF-8 source from regressions.
"""
from __future__ import annotations

import re
import unicodedata
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'static' / 'app.css').read_text(encoding='utf-8')
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


class _Elements(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.panels = set()
        self.go_targets = []
        self.nav_targets = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if 'id' in data:
            self.ids.append(data['id'])
        if tag == 'section' and data.get('id', '').startswith('panel-'):
            self.panels.add(data['id'].removeprefix('panel-'))
        if 'data-go' in data:
            self.go_targets.append(data['data-go'])
        if 'data-panel' in data:
            self.nav_targets.append(data['data-panel'])


class UIReadabilityTests(unittest.TestCase):
    def test_vietnamese_headline_is_valid_unicode(self):
        title = 'Viết truyện dễ hơn, giữ mạch truyện tốt hơn.'
        self.assertIn(title, HTML)
        self.assertEqual(title, unicodedata.normalize('NFC', title))
        self.assertEqual(HTML, unicodedata.normalize('NFC', HTML))
        self.assertIn('<meta charset="utf-8">', HTML)
        self.assertNotIn('\ufffd', HTML)

    def test_reading_fonts_are_native_vietnamese_sans(self):
        self.assertRegex(CSS, r'font-family:\s*"Segoe UI",\s*Tahoma,\s*Arial,\s*sans-serif')
        self.assertIn('.hero h2 {', CSS)
        self.assertIn('.manuscript {', CSS)
        self.assertIn('letter-spacing: 0;', CSS)

    def test_quickstart_buttons_map_to_working_panels(self):
        tree = _Elements()
        tree.feed(HTML)
        self.assertEqual(len(tree.ids), len(set(tree.ids)), 'HTML contains duplicate IDs')
        self.assertTrue({'outline', 'jobs', 'drafts'} <= set(tree.go_targets))
        self.assertTrue(set(tree.go_targets) <= tree.panels)
        self.assertTrue(set(tree.nav_targets) <= tree.panels)
        self.assertIn("document.querySelectorAll('[data-go]')", JS)
        self.assertIn("document.querySelectorAll('[data-panel]')", JS)

    def test_create_story_is_guided_and_keeps_existing_projects(self):
        tree = _Elements()
        tree.feed(HTML)
        for element in ('new-story-dialog', 'new-story-form', 'new-story-name',
                        'new-story-id', 'new-story-create', 'new-story-cancel'):
            self.assertIn(element, tree.ids)
        self.assertIn('friendlyStoryId(title)', JS)
        self.assertIn("title.normalize('NFD')", JS)
        self.assertNotIn("prompt('Tên truyện mới:", JS)
        self.assertIn("view('outline')", JS)

    def test_settings_uses_actual_runtime_port(self):
        for element in ('settings-local-url', 'settings-tailscale-command',
                        'settings-gateway-url'):
            self.assertIn('id="' + element + '"', HTML)
        self.assertIn("Number(x.settings?.port)||8765", JS)
        self.assertIn("$('settings-tailscale-command').textContent=", JS)

    def test_mobile_layout_and_keyboard_focus_are_present(self):
        self.assertIn('@media (max-width: 680px)', CSS)
        self.assertIn(':focus-visible', CSS)
        self.assertIn('.quickstart-grid { grid-template-columns: 1fr;', CSS)
        self.assertIn('prefers-reduced-motion', CSS)


if __name__ == '__main__':
    unittest.main()
