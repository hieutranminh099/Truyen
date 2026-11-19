"""Exercise the scene quality gates without Ollama, cloud credentials or a GPU."""
import json
import os
import time
from contextlib import closing
from itertools import cycle, islice
from unittest.mock import patch

# Base sets NOVEL_DATA_DIR before importing application modules.
from test_engine import Base, FakeAI

from novelengine.ai import ProviderError
from novelengine.config import project_dir
from novelengine.jobs import JobQueue
from novelengine.pipeline import process_scene, summarize_chapter, scene_packet
from novelengine.store import get_scene, now, save_outline, save_scene, story_db


REVIEW = {
    'critical': [],
    'style': ['Giữ nhịp vừa phải.'],
    'missing': [],
    'strengths': ['Chi tiết chiếc chuông nhất quán.'],
    'fixes': ['Chỉnh câu chuyển đoạn.'],
}
VALID_REVIEW = json.dumps(REVIEW, ensure_ascii=False)
CUT_REVIEW = '{"critical":[],"style":["Gợi ý chưa kết thúc'
WRONG_SCHEMA = json.dumps(dict(REVIEW, fixes=[{"text": "Không phải chuỗi"}]))
LEGACY_REVIEW = json.dumps({'unparsed': CUT_REVIEW})


def prose(word_count, first_word='An'):
    words = f'{first_word} nghe tiếng chuông đồng gỉ từ phía bến đò.'.split()
    return ' '.join(islice(cycle(words), word_count))


class ScriptedAI(FakeAI):
    def __init__(self, **scripts):
        super().__init__()
        scripts.setdefault('writer', [prose(250)])
        scripts.setdefault('editor', [prose(240, 'Linh')])
        self.scripts = {role: iter(responses) for role, responses in scripts.items()}
        self.requests = []

    def chat(self, system, user, **options):
        role = options['role']
        self.requests.append((role, user, options))
        if role not in self.scripts:
            return super().chat(system, user, **options)
        response = next(self.scripts[role])
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response()
        return response

    def requested_roles(self):
        return [role for role, _, _ in self.requests]


class PipelineQualityTests(Base):
    def setUp(self):
        super().setUp()
        self.chapter = self.outline['chapters'][0]
        self.scene = self.chapter['scenes'][0]
        self.scene['target_words'] = 250
        self.chapter_id = self.chapter['id']
        self.scene_id = self.scene['id']

    def run_scene(self, ai, **kwargs):
        return process_scene(self.pid, self.outline, self.chapter, self.scene, ai, **kwargs)

    def scene_state(self):
        with closing(story_db(self.pid)) as db:
            row = get_scene(db, self.chapter_id, self.scene_id)
            versions = [
                tuple(record) for record in db.execute(
                    'SELECT id, stage, text FROM scene_versions WHERE chapter=? AND scene=? ORDER BY id',
                    (self.chapter_id, self.scene_id),
                )
            ]
        return row, versions

    def assert_review(self, row, expected, **quality):
        stored = json.loads(row['review'])
        self.assertEqual(stored.pop('quality'), quality)
        self.assertEqual(stored, expected)

    def assert_unpublished(self):
        with closing(story_db(self.pid)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM summaries').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_items').fetchone()[0], 0)
        self.assertFalse(self.markdown_path().exists())

    def markdown_path(self):
        return project_dir(self.pid) / 'exports' / f'chapter_{self.chapter_id}.md'

    def use_single_scene_outline(self):
        self.chapter['scenes'] = [self.scene]
        self.outline['chapters'] = [self.chapter]
        save_outline(self.pid, self.outline)

    def wait_for_job(self, queue, job_id, state):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = next(row for row in queue.list(self.pid) if row['id'] == job_id)
            if job['state'] == state:
                return job
            if job['state'] == 'failed':
                self.fail(job['error'])
            time.sleep(.03)
        self.fail(f'Job {job_id} did not reach {state}: {queue.list(self.pid)}')

    def test_valid_critic_review_reaches_editor_once(self):
        draft, edited = prose(250), prose(235, 'Linh')
        ai = ScriptedAI(writer=[draft], critic=[VALID_REVIEW], editor=[edited])

        self.run_scene(ai)

        row, versions = self.scene_state()
        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor'])
        self.assertEqual(row['stage'], 'edited')
        self.assert_review(row, REVIEW, target_words=250, min_words=200, draft_words=250,
                           draft_too_short=False, edited_words=235, editor_min_words=200)
        self.assertIn(REVIEW['fixes'][0], ai.requests[-1][1])
        self.assertEqual([(stage, content) for _, stage, content in versions],
                         [('draft', draft), ('edited', edited)])
        self.assertIn(edited, self.markdown_path().read_text(encoding='utf-8'))

    def test_cut_json_retried_once_with_higher_bounded_budget(self):
        ai = ScriptedAI(critic=[CUT_REVIEW, VALID_REVIEW])
        ai.settings.tokens = 725

        self.run_scene(ai)

        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'critic', 'editor'])
        budgets = [options['max_tokens'] for role, _, options in ai.requests if role == 'critic']
        self.assertEqual(budgets, [650, 725])
        self.assertNotIn('Gợi ý chưa kết thúc', ai.requests[-1][1])

    def test_schema_rejects_wrong_field_types_and_never_calls_editor(self):
        malformed = [
            json.dumps(dict(REVIEW, critical='Không phải danh sách')),
            WRONG_SCHEMA,
        ]
        ai = ScriptedAI(critic=malformed)

        with self.assertRaisesRegex(RuntimeError, 'Critic') as failed:
            self.run_scene(ai)

        self.assertRegex(str(failed.exception).lower(), 'schema|cấu trúc')
        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'critic'])
        row, versions = self.scene_state()
        self.assertEqual(row['stage'], 'draft')
        self.assertEqual(row['review'], '')
        self.assertEqual(len(versions), 1)
        self.assert_unpublished()

    def test_repeated_cut_json_stops_without_discarding_draft(self):
        draft = prose(251)
        ai = ScriptedAI(writer=[draft], critic=[CUT_REVIEW, CUT_REVIEW])

        with self.assertRaisesRegex(RuntimeError, 'Critic') as failed:
            self.run_scene(ai)

        self.assertRegex(str(failed.exception).lower(), 'cắt|thiếu kết thúc')
        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'critic'])
        row, versions = self.scene_state()
        self.assertEqual((row['draft'], row['stage'], row['review']), (draft, 'draft', ''))
        self.assertEqual([content for _, _, content in versions], [draft])
        self.assert_unpublished()

    def test_legacy_unparsed_checkpoint_runs_critic_again(self):
        draft = prose(250)
        with closing(story_db(self.pid)) as db:
            save_scene(db, self.chapter_id, self.scene_id, 'draft', draft)
            save_scene(db, self.chapter_id, self.scene_id, 'review', LEGACY_REVIEW)
        ai = ScriptedAI(critic=[VALID_REVIEW])

        self.run_scene(ai)

        row, versions = self.scene_state()
        self.assertEqual(ai.requested_roles(), ['critic', 'editor'])
        self.assert_review(row, REVIEW, target_words=250, min_words=200, draft_words=250,
                           draft_too_short=False, edited_words=240, editor_min_words=200)
        self.assertNotIn('Gợi ý chưa kết thúc', ai.requests[-1][1])
        self.assertEqual([stage for _, stage, _ in versions], ['draft', 'edited'])

    def test_short_writer_warns_and_editor_can_reach_exact_threshold(self):
        draft, edited = prose(179), prose(200, 'Linh')
        ai = ScriptedAI(writer=[draft], editor=[edited])
        progress = []

        self.run_scene(ai, progress=progress.append)

        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor'])
        self.assertTrue(any('179' in message and '250' in message for message in progress), progress)
        row, versions = self.scene_state()
        self.assertEqual((row['draft'], row['edited']), (draft, edited))
        quality = json.loads(row['review'])['quality']
        self.assertEqual(quality, {'target_words': 250, 'min_words': 200, 'draft_words': 179,
                                   'draft_too_short': True, 'edited_words': 200, 'editor_min_words': 200})
        self.assertEqual([stage for _, stage, _ in versions], ['draft', 'edited'])

    def test_minimum_ratio_override_and_invalid_configuration(self):
        ai = ScriptedAI(writer=[prose(179)], editor=[prose(177, 'Linh')])
        with patch.dict(os.environ, {'NOVEL_SCENE_MIN_RATIO': 'NaN'}):
            with self.assertRaisesRegex(ValueError, 'NOVEL_SCENE_MIN_RATIO'):
                self.run_scene(ai)
        self.assertEqual(ai.requested_roles(), [])
        self.assertEqual(self.scene_state(), (None, []))

        with patch.dict(os.environ, {'NOVEL_SCENE_MIN_RATIO': '0.70'}):
            self.run_scene(ai)
        row, _ = self.scene_state()
        self.assertEqual(row['stage'], 'edited')
        self.assertEqual(json.loads(row['review'])['quality']['min_words'], 175)

    def test_punctuation_cannot_pad_word_count(self):
        editor_output = prose(164, 'Linh') + (' … — !' * 40)
        ai = ScriptedAI(writer=[prose(250)], editor=[editor_output])

        with self.assertRaisesRegex(RuntimeError, r'Editor.*164'):
            self.run_scene(ai)

        self.assert_unpublished()

    def test_repeated_underlength_edit_keeps_one_draft_and_reuses_review(self):
        draft, short = prose(179), prose(164, 'Linh')
        ai = ScriptedAI(writer=[draft], editor=[short, short])

        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, 'Editor') as failed:
                self.run_scene(ai)
            self.assertIn('164', str(failed.exception))
            self.assertIn('250', str(failed.exception))
            row, versions = self.scene_state()
            self.assertEqual((row['stage'], row['draft'], row['edited']), ('review', draft, ''))
            self.assertEqual([stage for _, stage, _ in versions], ['draft'])
            self.assert_unpublished()

        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor', 'editor'])

    def test_editor_cannot_remove_most_of_a_long_draft_to_reach_target(self):
        ai = ScriptedAI(writer=[prose(600)], editor=[prose(201, 'Linh')])

        with self.assertRaisesRegex(RuntimeError, 'Editor'):
            self.run_scene(ai)

        row, versions = self.scene_state()
        self.assertEqual(row['stage'], 'review')
        self.assertEqual(row['edited'], '')
        self.assertEqual([stage for _, stage, _ in versions], ['draft'])
        self.assert_unpublished()

    def test_empty_editor_result_resumes_from_valid_review(self):
        ai = ScriptedAI(critic=[VALID_REVIEW], editor=['  \n ', prose(250, 'Linh')])

        with self.assertRaisesRegex(RuntimeError, 'Editor'):
            self.run_scene(ai)

        row, versions = self.scene_state()
        self.assertEqual(row['stage'], 'review')
        self.assert_review(row, REVIEW, target_words=250, min_words=200, draft_words=250,
                           draft_too_short=False)
        self.assertEqual([stage for _, stage, _ in versions], ['draft'])
        self.assert_unpublished()

        self.run_scene(ai)

        recovered, updated_versions = self.scene_state()
        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor', 'editor'])
        self.assertEqual(recovered['stage'], 'edited')
        self.assertEqual(updated_versions[:-1], versions)

    def test_critic_network_error_marks_job_failed_then_resume_reuses_draft(self):
        self.use_single_scene_outline()
        ai = ScriptedAI(critic=[ProviderError('Ollama không phản hồi'), VALID_REVIEW])
        queue = JobQueue(ai, poll=.03)
        job_id = queue.submit(self.pid, 'series')
        queue.start()
        try:
            failed = self.wait_for_job(queue, job_id, 'failed')
            self.assertIn('Ollama không phản hồi', failed['error'])
            self.assertEqual(ai.requested_roles(), ['writer', 'critic'])
            row, versions = self.scene_state()
            self.assertEqual(row['stage'], 'draft')
            self.assert_unpublished()

            queue.command(job_id, 'resume')
            self.wait_for_job(queue, job_id, 'waiting_approval')
            recovered, updated_versions = self.scene_state()
            self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'critic', 'editor', 'summary'])
            self.assertEqual(recovered['draft'], row['draft'])
            self.assertEqual(recovered['stage'], 'edited')
            self.assertEqual(updated_versions[:-1], versions)
            self.assertEqual(len(updated_versions), 2)
            with closing(story_db(self.pid)) as db:
                self.assertEqual(db.execute('SELECT status FROM summaries').fetchone()[0], 'pending')
        finally:
            queue.shutdown()

    def test_invalid_summary_leaves_existing_scene_summary_and_canon_intact(self):
        self.use_single_scene_outline()
        self.run_scene(FakeAI())
        saved_scene = self.scene_state()
        markdown = self.markdown_path().read_bytes()
        with closing(story_db(self.pid)) as db, db:
            db.execute("INSERT INTO summaries VALUES(?, 'Tóm tắt cũ', 'stale', ?)",
                       (self.chapter_id, now()))
            db.execute(
                "INSERT INTO memory_items(kind, subject, content, chapter, source, status, created) "
                "VALUES('fact', 'An', 'Canon cũ', ?, 'model', 'approved', ?)",
                (self.chapter_id, now()),
            )

        def content():
            with closing(story_db(self.pid)) as db:
                return ([tuple(row) for row in db.execute('SELECT * FROM summaries')],
                        [tuple(row) for row in db.execute('SELECT * FROM memory_items')])

        saved_content = content()
        usable = {'kind': 'fact', 'subject': 'An', 'content': 'An nghe tiếng chuông.'}
        invalid_responses = [
            '[]', '{}', 'null', '42', '"văn bản"', '{"summary": "bị cắt',
            'Giải thích ngoài JSON {"summary":"Chương hợp lệ","proposals":[]}',
            json.dumps({'summary': '', 'proposals': []}),
            json.dumps({'summary': '  \n ', 'proposals': []}),
            json.dumps({'summary': 10, 'proposals': []}),
            json.dumps({'summary': 'Có nội dung'}),
            json.dumps({'summary': 'Có nội dung', 'proposals': {}}),
            json.dumps({'summary': 'Có nội dung', 'proposals': [usable] * 13}),
        ]
        for invalid in (None, 'văn bản', {}, dict(usable, kind=[]), dict(usable, kind='invalid'),
                        dict(usable, subject=123), dict(usable, subject='   '),
                        dict(usable, content=[]), dict(usable, content='  ')):
            invalid_responses.append(json.dumps({'summary': 'Có nội dung', 'proposals': [usable, invalid]}))

        for raw in invalid_responses:
            with self.subTest(raw=raw):
                ai = ScriptedAI(summary=[raw])
                with self.assertRaisesRegex(RuntimeError, 'Summary không hợp lệ.*tạo lại tóm tắt'):
                    summarize_chapter(self.pid, self.chapter, ai)
                self.assertEqual(ai.requested_roles(), ['summary'])
                self.assertEqual(content(), saved_content)
                self.assertEqual(self.scene_state(), saved_scene)
                self.assertEqual(self.markdown_path().read_bytes(), markdown)

    def test_summary_failure_then_resume_only_runs_summary_again(self):
        self.use_single_scene_outline()
        ai = ScriptedAI(critic=[VALID_REVIEW], summary=[
            '{"summary": "Chương trước", "proposals": null}',
            '```json\n{"summary": "An nghe tiếng chuông.", "proposals":[]}\n```',
        ])
        queue = JobQueue(ai, poll=.03)
        job_id = queue.submit(self.pid, 'series')
        queue.start()
        try:
            failed = self.wait_for_job(queue, job_id, 'failed')
            self.assertIn('Summary không hợp lệ', failed['error'])
            self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor', 'summary'])
            before = self.scene_state()
            self.assertEqual(before[0]['stage'], 'edited')
            self.assertEqual(len(before[1]), 2)
            markdown = self.markdown_path().read_bytes()
            with closing(story_db(self.pid)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM summaries').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_items').fetchone()[0], 0)

            queue.command(job_id, 'resume')
            self.wait_for_job(queue, job_id, 'waiting_approval')
            self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor', 'summary', 'summary'])
            self.assertEqual(self.scene_state(), before)
            self.assertEqual(self.markdown_path().read_bytes(), markdown)
            with closing(story_db(self.pid)) as db:
                summary = db.execute('SELECT body,status FROM summaries').fetchone()
                self.assertEqual(tuple(summary), ('An nghe tiếng chuông.', 'pending'))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_items').fetchone()[0], 0)
        finally:
            queue.shutdown()

    def test_restart_before_editor_commit_keeps_checkpoint(self):
        self.use_single_scene_outline()
        interrupted = ScriptedAI(critic=[VALID_REVIEW], editor=[SystemExit()])
        queue = JobQueue(interrupted, poll=.03)
        job_id = queue.submit(self.pid, 'series')
        queue.start()
        try:
            queue.thread.join(timeout=20)
            self.assertFalse(queue.thread.is_alive())
            self.assertEqual(queue.list(self.pid)[0]['state'], 'running')
            row, versions = self.scene_state()
            self.assertEqual(row['stage'], 'review')
            self.assert_review(row, REVIEW, target_words=250, min_words=200, draft_words=250,
                               draft_too_short=False)
            self.assertEqual(len(versions), 1)
            self.assert_unpublished()
        finally:
            queue.shutdown()

        recovered = ScriptedAI(editor=[prose(250, 'Linh')])
        restarted_queue = JobQueue(recovered, poll=.03)
        restarted_queue.start()
        try:
            self.wait_for_job(restarted_queue, job_id, 'waiting_approval')
            edited, updated_versions = self.scene_state()
            self.assertEqual(recovered.requested_roles(), ['editor', 'summary'])
            self.assert_review(edited, REVIEW, target_words=250, min_words=200, draft_words=250,
                               draft_too_short=False, edited_words=250, editor_min_words=200)
            self.assertEqual(updated_versions[:-1], versions)
            self.assertEqual(len(updated_versions), 2)
        finally:
            restarted_queue.shutdown()

    def test_concurrent_manual_edit_wins_over_editor_result(self):
        manual = 'Tác giả giữ nguyên bản sửa tay của mình.'

        def edit_manually():
            with closing(story_db(self.pid)) as db:
                save_scene(db, self.chapter_id, self.scene_id, 'edited', manual)
            return prose(250, 'Linh')

        ai = ScriptedAI(editor=[edit_manually])
        with self.assertRaisesRegex(RuntimeError, 'Cảnh đã thay đổi'):
            self.run_scene(ai)

        row, versions = self.scene_state()
        self.assertEqual(row['edited'], manual)
        self.assertEqual([(stage, content) for _, stage, content in versions],
                         [('draft', row['draft']), ('edited', manual)])

    def test_failed_rewrite_preserves_approved_scene_export_and_canon(self):
        self.run_scene(FakeAI())
        original, versions = self.scene_state()
        original_markdown = self.markdown_path().read_bytes()
        with closing(story_db(self.pid)) as db, db:
            db.execute("INSERT INTO summaries VALUES(?, 'Tóm tắt cũ', 'approved', ?)",
                       (self.chapter_id, now()))
            db.execute(
                "INSERT INTO memory_items(kind, content, chapter, source, status, created) "
                "VALUES('fact', 'Canon cũ', ?, 'model', 'approved', ?)",
                (self.chapter_id, now()),
            )

        for failed_ai, stage in ((ScriptedAI(critic=[CUT_REVIEW, WRONG_SCHEMA]), 'Critic'),
                                 (ScriptedAI(editor=[prose(164, 'Linh')]), 'Editor')):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(RuntimeError, stage):
                    self.run_scene(failed_ai, rewrite=True)
                self.assertEqual(self.scene_state(), (original, versions))
                self.assertEqual(self.markdown_path().read_bytes(), original_markdown)
                with closing(story_db(self.pid)) as db:
                    self.assertEqual(db.execute('SELECT status FROM summaries').fetchone()[0], 'approved')
                    self.assertEqual(db.execute('SELECT status FROM memory_items').fetchone()[0], 'approved')

        replacement = prose(250, 'Linh')
        self.run_scene(ScriptedAI(editor=[replacement]), rewrite=True)
        revised, revised_versions = self.scene_state()
        self.assertEqual(revised['edited'], replacement)
        self.assertEqual(revised_versions[:2], versions)
        self.assertEqual([stage for _, stage, _ in revised_versions[2:]], ['draft', 'edited'])
        with closing(story_db(self.pid)) as db:
            self.assertEqual(db.execute('SELECT status FROM summaries').fetchone()[0], 'stale')
            self.assertEqual(db.execute('SELECT status FROM memory_items').fetchone()[0], 'stale')

    def test_editor_must_keep_required_detail_and_retry_only_editor(self):
        """Enough words must not bypass an omitted must_include condition."""
        omitted = prose(250, 'Linh').replace('chuông đồng gỉ', 'tiếng mưa xa')
        corrected = prose(250, 'Linh')
        ai = ScriptedAI(critic=[VALID_REVIEW], editor=[omitted, corrected])

        with self.assertRaisesRegex(RuntimeError, 'Editor thiếu chi tiết bắt buộc'):
            self.run_scene(ai)
        row, versions = self.scene_state()
        self.assertEqual(row['stage'], 'review')
        self.assertEqual(row['edited'], '')
        self.assertEqual([stage for _, stage, _ in versions], ['draft'])
        self.assert_unpublished()

        self.run_scene(ai)
        row, versions = self.scene_state()
        self.assertEqual(row['edited'], corrected)
        self.assertEqual([stage for _, stage, _ in versions], ['draft', 'edited'])
        self.assertEqual(ai.requested_roles(), ['writer', 'critic', 'editor', 'editor'])

    def test_scene_packet_does_not_leak_later_chapters_or_revised_scenes(self):
        """The Writer never receives future approved memory, summaries or prose."""
        chapter_one, chapter_two = self.outline['chapters']
        first = chapter_one['scenes'][0]
        second = chapter_one['scenes'][1]
        future = chapter_two['scenes'][0]
        with closing(story_db(self.pid)) as db, db:
            save_scene(db, chapter_one['id'], first['id'], 'edited', 'CHUONG_MO_DAU', commit=False)
            save_scene(db, chapter_two['id'], future['id'], 'edited', 'SPOILER_CANH_SAU', commit=False)
            db.execute(
                "INSERT INTO summaries(chapter,body,status,updated) VALUES(?,?,'approved',?)",
                (chapter_one['id'], 'TOM_TAT_CHUONG_DAU', now()),
            )
            db.execute(
                "INSERT INTO summaries(chapter,body,status,updated) VALUES(?,?,'approved',?)",
                (chapter_two['id'], 'TOM_TAT_TUONG_LAI', now()),
            )
            for chapter, source, marker in [
                ('', 'manual', 'CANON_NEN_TANG'),
                (chapter_one['id'], 'model', 'CANON_CHUONG_DAU'),
                (chapter_two['id'], 'model', 'SPOILER_CANON_SAU'),
            ]:
                db.execute(
                    """INSERT INTO memory_items(kind,subject,content,chapter,source,status,created)
                       VALUES('fact','An',?,?,?,'approved',?)""",
                    (marker, chapter, source, now()),
                )
        packet, _ = scene_packet(self.pid, self.outline, chapter_one, second)
        self.assertIn('CHUONG_MO_DAU', packet)
        self.assertIn('CANON_NEN_TANG', packet)
        for secret in ('SPOILER_CANH_SAU', 'SPOILER_CANON_SAU', 'TOM_TAT_TUONG_LAI',
                       'CANON_CHUONG_DAU', 'TOM_TAT_CHUONG_DAU'):
            self.assertNotIn(secret, packet)
        self.assertNotIn('từng tham gia một nghi lễ đã quên', packet)

        future_packet, _ = scene_packet(self.pid, self.outline, chapter_two, future)
        self.assertIn('CANON_CHUONG_DAU', future_packet)
        self.assertIn('TOM_TAT_CHUONG_DAU', future_packet)
        self.assertNotIn('SPOILER_CANON_SAU', future_packet)
        self.assertNotIn('SPOILER_CANH_SAU', future_packet)
        self.assertNotIn('TOM_TAT_TUONG_LAI', future_packet)

    def test_regenerated_summary_marks_prior_approved_facts_stale_with_audit(self):
        """Approved canon must remain reviewable rather than silently revoked."""
        self.use_single_scene_outline()
        self.run_scene(FakeAI())
        with closing(story_db(self.pid)) as db, db:
            db.execute(
                "INSERT INTO summaries(chapter,body,status,updated) VALUES(?, 'Cũ', 'stale', ?)",
                (self.chapter_id, now()),
            )
            db.execute(
                """INSERT INTO memory_items(kind,subject,content,chapter,source,status,created)
                   VALUES('fact','An','CANON_DA_DUYET',?,'model','approved',?)""",
                (self.chapter_id, now()),
            )
            db.execute(
                """INSERT INTO memory_items(kind,subject,content,chapter,source,status,created)
                   VALUES('fact','An','DE_XUAT_CU',?,'model','pending',?)""",
                (self.chapter_id, now()),
            )
        self.assertEqual(summarize_chapter(self.pid, self.chapter, FakeAI()), 'pending')
        with closing(story_db(self.pid)) as db:
            rows = {r['content']: (r['id'], r['status']) for r in db.execute(
                "SELECT id,content,status FROM memory_items WHERE source='model'"
            )}
            self.assertEqual(rows['CANON_DA_DUYET'][1], 'stale')
            self.assertEqual(rows['DE_XUAT_CU'][1], 'revoked')
            old_id = rows['CANON_DA_DUYET'][0]
            history = [r['action'] for r in db.execute(
                "SELECT action FROM memory_audit WHERE item_id=?", (old_id,)
            )]
            self.assertIn('stale', history)
        packet, _ = scene_packet(self.pid, self.outline, self.chapter, self.scene)
        self.assertNotIn('CANON_DA_DUYET', packet)
