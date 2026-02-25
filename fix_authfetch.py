import os
import re

target_dir = "frontend/app"

for root, _, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".tsx") or file.endswith(".ts"):
            filepath = os.path.join(root, file)
            with open(filepath, "r") as f:
                content = f.read()
            
            # Skip if fetch is not used
            if "fetch(" not in content:
                continue
                
            # Skip if it's already using authFetch everywhere it needs to
            # But let's just do a blanket replacement of ' fetch(' or '= fetch('
            
            new_content = re.sub(r'\bfetch\(', 'authFetch(', content)
            
            # Add import if missing
            if "authFetch" in new_content and "import { authFetch" not in new_content and "import { API_BASE, authFetch }" not in new_content and "import {authFetch" not in new_content:
                # Add it after the first import or 'use client'
                lines = new_content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("import ") or line.startswith("'use client'"):
                        lines.insert(i + 1, "import { authFetch } from '@/lib/api';")
                        break
                new_content = "\n".join(lines)
                
            with open(filepath, "w") as f:
                f.write(new_content)

print("Replacement complete.")
