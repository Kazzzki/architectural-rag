
# patch_importlib.py
# Python 3.9以下での google-api-python-client 互換性パッチ

import sys
import importlib

if sys.version_info < (3, 10):
    try:
        import importlib_metadata
        
        # importlib.metadata 自体を importlib_metadata に置き換える
        sys.modules['importlib.metadata'] = importlib_metadata
        
        # importlib にも属性として設定
        importlib.metadata = importlib_metadata
        
        # 念のため packages_distributions も設定
        if not hasattr(importlib_metadata, 'packages_distributions'):
            importlib_metadata.packages_distributions = importlib_metadata.packages_distributions
            
        print("Patched importlib.metadata for Python 3.9 compatibility")
    except ImportError:
        print("WARNING: importlib_metadata not found. Google Drive API may fail.")
