from __future__ import annotations
import os
from security.keys import KeyStore

def test_key_digest_revoke_and_permissions(tmp_path):
    path=tmp_path/"keys.json";store=KeyStore(path,"x"*40);full,rec=store.create("test","viewer")
    assert store.verify(full).key_id==rec.key_id
    assert full.split(".")[1] not in path.read_text()
    if os.name!="nt":assert path.stat().st_mode & 0o777==0o600
    assert store.revoke(rec.key_id) and store.verify(full) is None
