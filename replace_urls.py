import os
import re

base_dir = r"d:\InvPro\dashboard\src"

for root, dirs, files in os.walk(base_dir):
    for file in files:
        if not file.endswith('.jsx'): continue
        if file == 'LiveDataContext.jsx': continue
        filepath = os.path.join(root, file)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if 'http://localhost:8000' in content:
            # Determine relative path to config.js
            # src is depth 0
            rel_path = os.path.relpath(filepath, base_dir)
            depth = len(rel_path.split(os.sep)) - 1
            if depth == 0:
                import_path = "./config"
            else:
                import_path = "../" * depth + "config"
                
            # Replace single quotes or double quotes around localhost
            content = re.sub(r"['\"]http://localhost:8000(.*?)['\"]", r"`${API_BASE_URL}\1`", content)
            
            # Add import after the first import or at the top
            import_stmt = f"import {{ API_BASE_URL }} from '{import_path}';\n"
            
            lines = content.split('\n')
            last_import = 0
            for i, line in enumerate(lines):
                if line.startswith('import '):
                    last_import = i
            
            lines.insert(last_import + 1, import_stmt)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"Updated {filepath}")
