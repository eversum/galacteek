from galacteek.ipfs.mimetype import MIMEType


def test_mime_valid():
    mType = MIMEType('text/plain')
    assert mType.valid is True
    assert mType.category == 'text'

    mType = MIMEType('text/html; charset=UTF-8')
    assert mType.valid is True

    mType = MIMEType('image')
    assert mType.valid is False
