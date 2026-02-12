
import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.append(os.getcwd())

from classifier import DocumentClassifier
from ocr_processor import finalize_processing
import config

class TestPhase1_2(unittest.TestCase):
    def setUp(self):
        self.classifier = DocumentClassifier()

    def test_classifier_validation(self):
        """Test that classifier validates categories and tags"""
        # Mock AI response with invalid category and tags
        input_data = {
            "primary_category": "invalid_category",  # Should be corrected to uploads
            "tags": ["建築基準法", "invalid_tag", "構造設計"], # invalid_tag should be removed
            "page_mapping": {}
        }
        
        # Mock _ai_classify to return this data
        with patch.object(self.classifier, '_ai_classify', return_value=input_data):
            result = self.classifier.classify("dummy text", {})
            
            print(f"\n[Validation Test] Result: {json.dumps(result, ensure_ascii=False)}")
            
            self.assertEqual(result['primary_category'], "uploads")
            self.assertIn("建築基準法", result['tags'])
            self.assertIn("構造設計", result['tags'])
            self.assertNotIn("invalid_tag", result['tags'])

    @patch('classifier.DocumentClassifier')
    @patch('indexer.index_file')
    @patch('shutil.move')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('pathlib.Path.exists', return_value=False)
    @patch('pathlib.Path.mkdir')
    def test_strict_folder_rules_uploads(self, mock_mkdir, mock_exists, mock_open, mock_move, mock_index, MockClassifier):
        """Test file in 'uploads' IS moved based on primary_category"""
        
        # Setup classifier mock
        mock_clf_instance = MockClassifier.return_value
        mock_clf_instance.classify.return_value = {
            "primary_category": "3_法規チェック/3-1_建築基準法（単体規定）",
            "tags": [],
            "page_mapping": {}
        }
        mock_clf_instance.generate_frontmatter.return_value = "---\n---\n"
        
        # Mock config
        config.KNOWLEDGE_BASE_DIR = Path("/data/kb")
        config.ENABLE_AUTO_CATEGORIZE = True
        
        # Scenario: File in uploads
        filepath = "/data/kb/uploads/test.pdf"
        output_path = "/data/kb/uploads/test.md"
        
        # Execute
        new_pdf, new_md = finalize_processing(filepath, output_path, "content")
        
        # Verify strict move
        # Should be moved to 3_法規チェック/3-1_建築基準法（単体規定）
        expected_dir = Path("/data/kb/3_法規チェック/3-1_建築基準法（単体規定）")
        self.assertIn(str(expected_dir), str(new_pdf))
        print(f"\n[Uploads Test] File moved to: {new_pdf}")

    @patch('classifier.DocumentClassifier')
    @patch('indexer.index_file')
    @patch('shutil.move')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('pathlib.Path.exists', return_value=False)
    @patch('pathlib.Path.mkdir')
    def test_strict_folder_rules_non_uploads(self, mock_mkdir, mock_exists, mock_open, mock_move, mock_index, MockClassifier):
        """Test file NOT in 'uploads' is NOT moved even if category fits"""
        
        # Setup classifier mock
        mock_clf_instance = MockClassifier.return_value
        mock_clf_instance.classify.return_value = {
            "primary_category": "3_法規チェック/3-1_建築基準法（単体規定）", # Fits perfectly
            "tags": [],
            "page_mapping": {}
        }
        mock_clf_instance.generate_frontmatter.return_value = "---\n---\n"
        
        # Mock config
        config.KNOWLEDGE_BASE_DIR = Path("/data/kb")
        config.ENABLE_AUTO_CATEGORIZE = True
        
        # Scenario: File already in specific folder
        filepath = "/data/kb/99_その他/test.pdf"
        output_path = "/data/kb/99_その他/test.md"
        
        # Execute
        new_pdf, new_md = finalize_processing(filepath, output_path, "content")
        
        # Verify NO move
        self.assertEqual(str(new_pdf), filepath)
        print(f"\n[Non-Uploads Test] File kept at: {new_pdf}")

if __name__ == '__main__':
    unittest.main()
