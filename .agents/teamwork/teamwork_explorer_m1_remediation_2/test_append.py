import pathlib

p1 = pathlib.Path(".agents/teamwork/teamwork_explorer_m1_remediation_2/test_append_1.txt")
p2 = pathlib.Path(".agents/teamwork/teamwork_explorer_m1_remediation_2/test_append_2.txt")
p3 = pathlib.Path(".agents/teamwork/teamwork_explorer_m1_remediation_2/test_append_3.txt")

with p1.open("a", encoding="utf-8") as f:
    f.write("line1\nline2\n")
print("append1 (open 'a' default) raw:", repr(p1.read_bytes()))

with p2.open("a", encoding="utf-8", newline="\n") as f:
    f.write("line1\nline2\n")
print("append2 (open 'a' newline='\\n') raw:", repr(p2.read_bytes()))

with p3.open("ab") as f:
    f.write("line1\nline2\n".encode("utf-8"))
print("append3 (open 'ab') raw:", repr(p3.read_bytes()))
