import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluation_scenes import load_scenes, to_outline
from novelengine.outline import parse_outline


class EvaluationTests(unittest.TestCase):
    def test_original_scenes_convert_to_app_outline(self):
        dataset = load_scenes()
        self.assertGreaterEqual(len(dataset['scenes']), 12)
        self.assertEqual(len({scene['genre'] for scene in dataset['scenes']}), len(dataset['scenes']))
        self.assertEqual(len(parse_outline(to_outline(dataset))['chapters']), len(dataset['scenes']))
        selected = to_outline(dataset, ['trinh-tham'])
        self.assertEqual([chapter['id'] for chapter in selected['chapters']], ['trinh-tham'])
        self.assertTrue(selected['chapters'][0]['scenes'][0]['continuity_requirements'])

    def test_validator_rejects_duplicates_and_incomplete_scenes(self):
        dataset = load_scenes()
        variants = [copy.deepcopy(dataset), copy.deepcopy(dataset)]
        variants[0]['scenes'][1]['id'] = variants[0]['scenes'][0]['id']
        del variants[1]['scenes'][0]['criteria']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            for variant in variants:
                path.write_text(json.dumps(variant), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_scenes(path)
