import os
import ast
from typing import Dict,Any
import importlib.util

class CodeParser:
    def __init__(self, project_dir):
        self.project_dir = os.path.abspath(project_dir)
        self.all_files = self.get_all_files(include_ext={'.py'})

    def get_all_files(self, include_ext=None, ignore_hidden=True, follow_symlinks=False):
        files = {}
        for root, dirs, file_names in os.walk(self.project_dir, followlinks=follow_symlinks):
            if ignore_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for name in file_names:
                if ignore_hidden and name.startswith('.'):
                    continue
                if include_ext and not os.path.splitext(name)[1] in include_ext:
                    continue
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, self.project_dir)
                files[rel_path] = abs_path
            for name in dirs:
                if ignore_hidden and name.startswith('.'):
                    continue
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, self.project_dir)
                files[rel_path] = abs_path
        return files

    def extract_imports_from_file(self, file_path:str)->Dict[str,Any]:
        if not os.path.exists(file_path):
            print(f"[DEBUG] File not found: {file_path}")
            return {"Error": "File not found."}
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=file_path)
            except Exception as e:
                print(f"[DEBUG] Error parsing AST for {file_path}: {e}")
                return {"Error": "AST parsing failed."}
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    top_module = node.module.split('.')[0]
                    if top_module not in imports:
                        imports[top_module] = set()
                    for alias in node.names:
                        imports[top_module].add(alias.name)
        return imports if imports else {"Info": "No imports found."}

    def resolve_import_paths(self, imports:Dict[str,Any])->Dict[str,Any]:
        result = {}
        for module, names in imports.items():
            if module in ["Error", "Info"]:  
                continue
            py_file = module + '.py'
            found = False
            for rel_path,abs_path in self.all_files.items():
                if os.path.basename(rel_path)==py_file:
                    result[rel_path]=abs_path
                    found = True
                    break 
            if found:
                continue
            else:
                found_path = ""
                for rel_path,abs_path in self.all_files.items():
                    if os.path.basename(rel_path)==module:
                        found_path = abs_path
                        break
                if found_path.strip(): 
                    init_file = os.path.join(found_path, "__init__.py")
                    if os.path.exists(init_file):
                        rel_init = os.path.join(module, "__init__.py")
                        result[rel_init] = init_file
                        try:
                            with open(init_file, "r", encoding="utf-8") as f:
                                tree = ast.parse(f.read(), filename=init_file)
                        except Exception as e:
                            print(f"[DEBUG] Failed to parse {init_file}: {e}")
                            continue
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ImportFrom) and node.module:
                                for alias in node.names:
                                    if alias.name in names:
                                        sub_file = node.module.split('.')[0] + ".py"
                                        sub_path = os.path.join(found_path, sub_file)
                                        if os.path.exists(sub_path):
                                            rel_sub = os.path.join(module, sub_file)
                                            result[rel_sub] = sub_path
                                        else:
                                            print(f"[DEBUG] Submodule file not found: {sub_file}")
        return result if result else {"Info": "No import paths resolved."}

if __name__ == "__main__":
    project_dir = "C:/Users/Debajyoti/OneDrive/Desktop/Jarves full agent"
    code_parser = CodeParser(project_dir=project_dir)

    all_files = code_parser.get_all_files(include_ext={".py", ".txt", ".json"})
    print("Project Structure:")
    print(all_files)

    print("\n=============================================\n")
    test_file = os.path.join(project_dir, "jarves_test.py")
    imports = code_parser.extract_imports_from_file(file_path=test_file)
    print("Import modules from File:")
    print(imports)

    print("\n=============================================\n")
    resolved_imports = code_parser.resolve_import_paths(imports=imports)
    print("Resolved Imports from files:")
    print(resolved_imports)
