"""Regression tests for the second connector audit (isolated Hermes test home)."""
import concurrent.futures
import json
import pathlib
import tempfile
import unittest
from unittest import mock
from _helpers import load, make_png
store, tools, export = load('store'), load('tools'), load('export')

class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix='cr-integrity-'))
        self.path = make_png(self.tmp / 'image.png')
        self.a = store.create_board('A')['id']
        self.b = store.create_board('B')['id']
        self.image = store.add_image(self.a, str(self.path))
        self.foreign = store.add_image(self.b, str(self.path))

    def test_foreign_and_missing_approvals_fail_without_changes(self):
        for iid in [self.foreign['id'], 'img_missing']:
            with self.assertRaises(ValueError):
                store.set_approval(self.a, iid, 'approved')
        self.assertIsNone(store.get_approval(self.a))
        self.assertEqual(store.get_image(self.foreign['id'])['role'], 'generated')

    def test_cross_board_brief_and_revision_rejected(self):
        result = json.loads(tools.revision_brief({'board_id': self.a, 'image_id': self.foreign['id']}))
        self.assertFalse(result['ok'])
        with self.assertRaises(ValueError):
            store.create_revision(self.a, self.foreign['id'], 'bad')
        self.assertEqual(store.get_board(self.a)['revisions'], [])

    def test_unknown_revision_delivery_rejected(self):
        with self.assertRaises(ValueError):
            store.mark_revision_delivered('rev_missing')

    def test_rejected_and_unapproved_export_do_not_label_image_approved(self):
        for decision in [None, 'rejected']:
            if decision: store.set_approval(self.a, self.image['id'], decision)
            result = export.export_board(store.get_board(self.a), out_dir=str(self.tmp / 'out'))
            self.assertIsNone(result['approved_image_export'])
            bundle = json.loads(pathlib.Path(result['written'][0]).read_text())
            self.assertIsNone(bundle['approved_image_id'])

    def test_export_destinations_are_unique(self):
        store.set_approval(self.a, self.image['id'], 'approved')
        results = [export.export_board(store.get_board(self.a), out_dir=str(self.tmp / 'out')) for _ in range(2)]
        self.assertNotEqual(results[0]['written'], results[1]['written'])
        self.assertNotEqual(results[0]['approved_image_export'], results[1]['approved_image_export'])

    def test_concurrent_annotation_numbers_unique(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda n: store.add_annotation(self.image['id'], .1, .2, str(n)), range(24)))
        self.assertEqual(sorted(row['number'] for row in rows), list(range(1, 25)))

    def test_fake_and_oversized_images_rejected(self):
        fake = self.tmp / 'fake.png'; fake.write_text('not image content')
        with self.assertRaises(ValueError): store.add_image(self.a, str(fake))
        with mock.patch.object(store, 'MAX_IMAGE_BYTES', 1):
            with self.assertRaises(ValueError): store.add_image(self.a, str(self.path))

    def test_relative_paths_rejected(self):
        with self.assertRaises(ValueError): store.add_image(self.a, 'docs/banner.png')

    def test_nonfinite_coordinates_rejected(self):
        for x in [float('nan'), float('inf')]:
            with self.assertRaises(ValueError): store.add_annotation(self.image['id'], x, .5)

    def test_invalid_decision_and_preapproved_import_rejected(self):
        with self.assertRaises(ValueError): store.set_approval(self.a, self.image['id'], 'oops')
        with self.assertRaises(ValueError): store.add_image(self.a, str(self.path), role='approved')

if __name__ == '__main__': unittest.main()
