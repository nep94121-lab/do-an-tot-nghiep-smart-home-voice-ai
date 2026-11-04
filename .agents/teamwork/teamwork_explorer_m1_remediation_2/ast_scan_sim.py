import ast
import pathlib

def ast_scan_sim():
    sim_dir = pathlib.Path("simulator")
    py_files = sorted(sim_dir.rglob("*.py"))
    
    ast_findings = []
    
    class WriteVisitor(ast.NodeVisitor):
        def __init__(self, filename):
            self.filename = filename
            
        def visit_Call(self, node):
            # check method calls
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                if method_name in ("write_text", "write_bytes", "dump", "dumps"):
                    ast_findings.append({
                        "file": self.filename,
                        "line": node.lineno,
                        "method": method_name,
                        "node_str": ast.unparse(node)
                    })
                elif method_name in ("open",):
                    ast_findings.append({
                        "file": self.filename,
                        "line": node.lineno,
                        "method": f".open()",
                        "node_str": ast.unparse(node)
                    })
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in ("open",):
                    ast_findings.append({
                        "file": self.filename,
                        "line": node.lineno,
                        "method": "open()",
                        "node_str": ast.unparse(node)
                    })
            self.generic_visit(node)

    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=f.as_posix())
            visitor = WriteVisitor(f.as_posix())
            visitor.visit(tree)
        except Exception as e:
            print(f"Error parsing {f}: {e}")

    return ast_findings

if __name__ == "__main__":
    findings = ast_scan_sim()
    print(f"AST Scan Results (Total: {len(findings)}):")
    for item in findings:
        # filter out json.dumps / etc unless it's writing or open
        if item["method"] == "dumps":
            continue
        print(f"[{item['method']}] {item['file']}:{item['line']} -> {item['node_str']}")
