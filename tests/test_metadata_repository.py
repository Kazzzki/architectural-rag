
import unittest
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.getcwd())

from database import init_db, get_session, LegacyDocument, Document, DocumentVersion, Upload, Artifact
from metadata_repository import MetadataRepository

class TestMetadataRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure DB is initialized
        init_db()

    def setUp(self):
        self.repo = MetadataRepository()
        self.session = get_session()

    def tearDown(self):
        # We don't necessarily want to wipe the real DB if it's being used, 
        # but for testing we should ideally use a temp one.
        # However, for this environment, let's just clean up our test records.
        self.session.close()

    def test_create_document_version_double_write(self):
        filename = f"test_doc_{os.urandom(4).hex()}.pdf"
        file_path = f"uploads/{filename}"
        source_pdf_hash = os.urandom(16).hex()
        
        result = self.repo.create_document_version(
            filename=filename,
            file_path=file_path,
            source_pdf_hash=source_pdf_hash,
            file_size=1024
        )
        
        self.assertIn("version_id", result)
        self.assertIn("document_id", result)
        self.assertIn("legacy_id", result)
        
        # Verify LegacyDocument
        legacy_doc = self.session.query(LegacyDocument).filter(LegacyDocument.file_path == file_path).first()
        self.assertIsNotNone(legacy_doc)
        self.assertEqual(legacy_doc.source_pdf_hash, source_pdf_hash)
        
        # Verify Document (New)
        doc = self.session.query(Document).filter(Document.id == result["document_id"]).first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.title, filename.rsplit('.', 1)[0])
        
        # Verify DocumentVersion (New)
        version = self.session.query(DocumentVersion).filter(DocumentVersion.id == result["version_id"]).first()
        self.assertIsNotNone(version)
        self.assertEqual(version.version_hash, source_pdf_hash)
        
        # Verify Upload (New)
        upload = self.session.query(Upload).filter(Upload.version_id == version.id).first()
        self.assertIsNotNone(upload)
        self.assertEqual(upload.original_filename, filename)

    def test_save_artifact(self):
        # First create a version
        v_res = self.repo.create_document_version("test_art.pdf", "test_art.pdf", "hash_art_test")
        v_id = v_res["version_id"]
        
        art_id = self.repo.save_artifact(
            version_id=v_id,
            artifact_type="ocr_markdown",
            storage_path="/tmp/test_art.md"
        )
        
        self.assertIsNotNone(art_id)
        
        artifact = self.session.query(Artifact).filter(Artifact.id == art_id).first()
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.artifact_type, "ocr_markdown")
        self.assertEqual(artifact.storage_path, "/tmp/test_art.md")

    def test_update_status_cascading(self):
        filename = "test_status.pdf"
        file_path = "uploads/test_status.pdf"
        v_res = self.repo.create_document_version(filename, file_path, "hash_status")
        
        # Mark as searchable
        self.repo.mark_as_searchable(file_path)
        
        # Verify Legacy
        legacy_doc = self.session.query(LegacyDocument).filter(LegacyDocument.file_path == file_path).first()
        self.assertEqual(legacy_doc.status, "completed")
        
        # Verify New
        version = self.session.query(DocumentVersion).filter(DocumentVersion.id == v_res["version_id"]).first()
        self.assertEqual(version.ingest_status, "searchable")
        self.assertTrue(version.searchable)

if __name__ == "__main__":
    unittest.main()
