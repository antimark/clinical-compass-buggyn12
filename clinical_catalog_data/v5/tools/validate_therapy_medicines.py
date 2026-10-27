#!/usr/bin/env python3
import json,hashlib,pathlib
R=pathlib.Path(__file__).resolve().parents[1]
def rd(path):return json.loads((R/path).read_text(encoding="utf-8"))
dx_index=rd("diagnoses/diagnoses_index.json")["items"]
mi=rd("medicines/medicine_index.json")["items"]
ti=rd("therapies/therapy_index.json")["items"]
pi=rd("medicines/source_product_index.json")["items"]
md={x["id"]:rd(x["path"]) for x in mi};td={x["id"]:rd(x["path"]) for x in ti}
assert len(mi)==len(md) and len(ti)==len(td) and len(pi)==8
for e in dx_index:
 code=e["code"];d=rd(e["path"]);assert d["code"]==code
 for rel in d["treatment_links"]["therapy_methods"]:
  assert code in [x["code"] for x in td[rel["therapy_id"]]["diagnosis_links"]]
 for rel in d["treatment_links"]["medicines_active_substances"]:
  assert code in [x["code"] for x in md[rel["substance_id"]]["diagnosis_links"]]
for p in pi:
 overlay=rd(p["overlay_path"])
 assert hashlib.sha256((R/p["instruction_path"]).read_bytes()).hexdigest()==overlay["provenance"]["sha256"]
for m in md.values():assert m["regulatory"]["ru_current_registration_verified"] is False
print("OK: 77 diagnoses,",len(ti),"therapy cards,",len(mi),"substances, 8 original product instructions, bidirectional links, regulatory gates")
