"""Static check of environment attributes used by deliverable controller code."""
import ast
from pathlib import Path

allowed = {'reset','get_state','get_goal','step','action_space','observation_space','close'}
for filename in ('controllers.py','tool_control.py'):
    tree=ast.parse(Path(filename).read_text())
    uses=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Attribute):
            base=node.value
            is_env=(isinstance(base,ast.Name) and base.id in ('env','e')) or (isinstance(base,ast.Attribute) and base.attr=='env')
            if is_env:
                assert node.attr in allowed, (filename,node.lineno,node.attr)
                uses.append(node.attr)
    print(filename, sorted(set(uses)))
