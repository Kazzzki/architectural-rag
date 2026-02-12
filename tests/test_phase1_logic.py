
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.append(os.getcwd())

from ocr_processor import finalize_processing
import config

class TestFileOrganization(unittest.TestCase):
    def setUp(self):
        self.status_mgr = MagicMock()
        self.mock_classifier = MagicMock()
        
    @patch('classifier.DocumentClassifier')
    @patch('indexer.index_file')
    @patch('shutil.move')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('pathlib.Path.exists', return_value=False)
    @patch('pathlib.Path.mkdir')
    def test_pattern_1_explicit_category(self, mock_mkdir, mock_exists, mock_open, mock_move, mock_index, mock_class_cls):
        """Pattern 1: Explicit category (e.g. 03_技術基準) -> Keep in folder"""
        # Setup
        mock_classifier = mock_class_cls.return_value
        mock_classifier.classify.return_value = {'content_domain': ['01_カタログ']} # Predicts generic but should be ignored
        mock_classifier.generate_frontmatter.return_value = "---\n---\n"
        
        filepath = str(config.KNOWLEDGE_BASE_DIR / "03_技術基準" / "data.pdf")
        output_path = str(config.KNOWLEDGE_BASE_DIR / "03_技術基準" / "data.md")
        
        # Execute
        finalize_processing(filepath, output_path, "md content", self.status_mgr)
        
        # Verify
        # Should NOT move if logic works (because it is in 03_技術基準 which is NOT uploads)
        # However, the code calculates target_dir. If target_dir == current_dir, it prints "移動不要".
        # Let's check the args to shultil.move if it was called.
        
        # Logic in updated ocr_processor:
        # original_category = "03_技術基準"
        # is_uploads = False
        # AUTO_CATEGORIZE_UPLOADS_ONLY = True (default)
        # -> category_path = "03_技術基準"
        # target_dir = KNOWLEDGE_BASE_DIR / "03_技術基準"
        # new_pdf_path = target_dir / "data.pdf"
        # which is same as filepath.
        # So shutil.move should NOT be called (or check equality and skip).
        
        mock_move.assert_not_called()
        print("Pattern 1 Test Passed: File remained in 03_技術基準")

    @patch('classifier.DocumentClassifier')
    @patch('indexer.index_file')
    @patch('shutil.move')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('pathlib.Path.exists', return_value=False)
    @patch('pathlib.Path.mkdir')
    def test_pattern_2_uploads_folder(self, mock_mkdir, mock_exists, mock_open, mock_move, mock_index, mock_class_cls):
        """Pattern 2: Uploads folder -> Auto classify"""
        # Setup
        mock_classifier = mock_class_cls.return_value
        mock_classifier.classify.return_value = {'content_domain': ['01_カタログ']} # Predicts Catalog
        mock_classifier.generate_frontmatter.return_value = "---\n---\n"
        
        filepath = str(config.KNOWLEDGE_BASE_DIR / "uploads" / "unknown.pdf")
        output_path = str(config.KNOWLEDGE_BASE_DIR / "uploads" / "unknown.md")
        
        # Execute
        finalize_processing(filepath, output_path, "md content", self.status_mgr)
        
        # Verify
        # Should move to 01_カタログ
        # target_dir = KNOWLEDGE_BASE_DIR / "01_カタログ"
        expected_pdf = config.KNOWLEDGE_BASE_DIR / "01_カタログ" / "unknown.pdf"
        
        # mock_move should be called
        self.assertTrue(mock_move.called)
        args, _ = mock_move.call_args_list[0]
        self.assertEqual(str(args[1]), str(expected_pdf))
        print("Pattern 2 Test Passed: File moved from uploads to 01_カタログ")

if __name__ == '__main__':
    unittest.main()
