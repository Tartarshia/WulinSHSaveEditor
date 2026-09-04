"""No-save-file test for the public source tree."""
from pathlib import Path
from tempfile import TemporaryDirectory

import es3_codec

sample = {"Data": {"value": {"createdCharacter": {"100401": {"m_surName": "测试", "m_givenName": "主角"}, "-1": {"m_isAlive": True}}}}}
with TemporaryDirectory() as directory:
    path = Path(directory) / "sample.save"
    es3_codec.atomic_write(path, sample)
    assert es3_codec.load(path) == sample
print("PASS: public ES3 AES/GZip write and read-back test")
