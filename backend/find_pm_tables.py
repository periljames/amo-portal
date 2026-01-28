import re, glob
paths = glob.glob(r"amodb/alembic/versions/*.py")
hits=[]
pat = re.compile(r"op\.create_table\(\s*['\"]([^'\"]+)['\"]", re.M)
for p in paths:
    s=open(p,'r',encoding='utf-8').read()
    for m in pat.finditer(s):
        if m.group(1) in ("part_movement_ledger","removal_events"):
            hits.append((p,m.group(1)))
print("\n".join([f"{p}  creates  {t}" for p,t in hits]) or "No create_table() found for those tables")
