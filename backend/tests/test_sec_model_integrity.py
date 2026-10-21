from __future__ import annotations
from security.model_integrity import sign_file,verify_file

def test_signed_model_detects_tampering(tmp_path):
    p=tmp_path/"model.bin";p.write_bytes(b"model bytes");sign_file(p,"s"*40)
    assert verify_file(p,"s"*40);p.write_bytes(b"tampered")
    assert not verify_file(p,"s"*40)
