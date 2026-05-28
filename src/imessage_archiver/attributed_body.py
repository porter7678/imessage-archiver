"""
Extract plain text from an iMessage attributedBody BLOB.

All modern iOS attributedBody blobs use Apple's streamtyped format, which encodes
an NSAttributedString. The plain text string (an NSString) is embedded after a
'+' (0x2b) marker byte, preceded by a varint length.

Varint encoding (little-endian):
  byte < 0x80      → value is the byte itself
  0x81 lo hi       → (hi << 8) | lo
  0x82 b0 b1 b2 b3 → 32-bit little-endian
"""

_STREAMTYPED_MAGIC = b"\x04\x0bstreamtyped"
_NSSTRING_MARKER = b"NSString"
_STRING_START = 0x2B  # '+' byte in the typedstream encoding


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Return (value, new_pos)."""
    b = data[pos]
    if b < 0x80:
        return b, pos + 1
    n_extra = b - 0x80  # 0x81 → 1 extra byte, 0x82 → 2, etc.
    val = int.from_bytes(data[pos + 1 : pos + 1 + n_extra], "little")
    return val, pos + 1 + n_extra


def extract_text(blob: bytes | None) -> tuple[str | None, str]:
    """
    Return (text, source) where source is one of:
      'attributed_body'  — successfully decoded
      'empty'            — blob present but no text found
      'null'             — blob was None/empty
    """
    if not blob:
        return None, "null"

    if not blob.startswith(_STREAMTYPED_MAGIC):
        # Unknown format — fall back to best-effort UTF-8 extraction
        try:
            return blob.decode("utf-8", errors="ignore") or None, "attributed_body"
        except Exception:
            return None, "empty"

    # Find NSString class marker in the blob
    ns_pos = blob.find(_NSSTRING_MARKER)
    if ns_pos == -1:
        return None, "empty"

    # Scan up to 25 bytes past NSString for the '+' (0x2b) string-start byte.
    # The intervening bytes are: version(1) + structural byte(1) + cache-ref(2) = 4 bytes.
    # We use a small window to avoid false matches from string content later in the blob.
    search_end = min(ns_pos + len(_NSSTRING_MARKER) + 25, len(blob))
    plus_pos = -1
    for i in range(ns_pos + len(_NSSTRING_MARKER), search_end):
        if blob[i] == _STRING_START:
            plus_pos = i
            break

    if plus_pos == -1 or plus_pos + 1 >= len(blob):
        return None, "empty"

    try:
        length, text_start = _read_varint(blob, plus_pos + 1)
    except (IndexError, ValueError):
        return None, "empty"

    if length == 0 or text_start + length > len(blob):
        return None, "empty"

    text_bytes = blob[text_start : text_start + length]
    try:
        text = text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = text_bytes.decode("utf-8", errors="replace")

    # Strip the Unicode object-replacement character (U+FFFC) used as attachment
    # placeholder when it's the *only* content — keep it when mixed with real text.
    stripped = text.replace("￼", "").strip()
    if not stripped:
        # Pure attachment placeholder; still return the marker so callers know
        # the message text is ￼ (attachment inline)
        return text.strip() or None, "attributed_body"

    return text, "attributed_body"
