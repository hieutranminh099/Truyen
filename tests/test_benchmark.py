import csv
import json
import tempfile
from pathlib import Path

from benchmark_models import CRITERIA, run_benchmark, summarize, write_csv
from test_engine import Base


class BenchmarkTests(Base):
    def test_mock_blind_outputs_and_human_score_export(self):
        with tempfile.TemporaryDirectory() as folder:
            run = run_benchmark(self.pid, ['fixture:a', 'fixture:b'], 2, 42,
                                mock=True, output=Path(folder))
            key = json.loads((run / 'bang_dap_an_RIENG.json').read_text(encoding='utf-8'))
            self.assertEqual(key['mode'], 'mock')
            self.assertEqual(len(key['samples']), 4)
            for draft in run.glob('canh_*.md'):
                self.assertNotIn('fixture:', draft.read_text(encoding='utf-8'))
            for scene in (1, 2):
                self.assertEqual(len({row['prompt_sha256'] for row in key['samples']
                                      if row['scene'] == scene}), 1)
            with self.assertRaisesRegex(ValueError, 'Chưa có điểm'):
                summarize(run, run / 'scores.csv')
            with (run / 'scores.csv').open(encoding='utf-8-sig') as stream:
                scores = list(csv.DictReader(stream))
            for row in scores:
                row['rater'] = 'reader-1'
                row.update(dict.fromkeys(CRITERIA, 3 if row['scene'] == '1' else 5))
            write_csv(run / 'scores.csv', list(scores[0]), scores)
            summary = summarize(run, run / 'scores.csv')
            self.assertEqual(len(summary), 14)
            self.assertTrue(all(row['mean'] == 4 and row['stdev'] == 1.4142 for row in summary))
            self.assertTrue((run / 'summary_RIENG.csv').is_file())
            scores[0][CRITERIA[0]] = 9
            write_csv(run / 'scores.csv', list(scores[0]), scores)
            with self.assertRaisesRegex(ValueError, 'không hợp lệ'):
                summarize(run, run / 'scores.csv')
