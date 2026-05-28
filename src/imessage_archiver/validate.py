def run(stats: dict):
    convs = stats["conversations_raw"]
    total_msgs = stats["total_messages"]

    print("\n" + "=" * 60)
    print("MILESTONE 1 VALIDATION REPORT")
    print("=" * 60)

    print(f"\nConversations:  {stats['total_conversations']}")
    print(f"Total messages: {total_msgs}")

    print("\n--- Message text source ---")
    pct = lambda n: f"{n:6d}  ({100*n/total_msgs:.1f}%)" if total_msgs else f"{n:6d}"
    print(f"  text column:      {pct(stats['text_source_text'])}")
    print(f"  attributedBody:   {pct(stats['text_source_attributed'])}")
    print(f"  empty (both null):{pct(stats['text_source_empty'])}")

    confirmed_blank = stats.get("empty_confirmed_blank", 0)
    both_null = stats.get("empty_both_null", 0)
    system_events = stats["text_source_empty"] - confirmed_blank - both_null
    if confirmed_blank:
        print(f"     ({confirmed_blank} have attributedBody with zero-length NSString = intentional blank sends, ok)")
    if system_events > 0:
        print(f"     ({system_events} are system events / group actions, expected)")
    if both_null > 0:
        print(
            f"\n  *** {both_null} messages have BOTH text and attributedBody NULL"
            " (may be SharePlay/GamePigeon/etc. — review if unexpected)"
        )

    unresolved = sorted(stats["unresolved_handles"])
    print(f"\n--- Unresolved handles: {len(unresolved)} ---")
    for h in unresolved[:10]:
        print(f"  {h}")
    if len(unresolved) > 10:
        print(f"  ... and {len(unresolved) - 10} more")

    print("\n--- Sample messages (first 3 from 2 conversations) ---")
    shown = 0
    for conv in convs:
        if shown >= 2:
            break
        style_label = f"[{conv['style']}]"
        print(f"\n  {style_label} {conv['title']!r}  (chat_id={conv['chat_id']})")
        for msg in conv["messages"][:3]:
            ts = msg["timestamp"] or "?"
            sender = msg["sender_name"]
            text = (msg["text"] or "").replace("\n", " ")[:120]
            src = msg["text_source"]
            print(f"    {ts}  {sender}: {text!r}  [{src}]")
        shown += 1

    cfg = __import__('imessage_archiver.config', fromlist=['JSON_INDEX', 'JSON_CONVERSATIONS_DIR'])
    print(f"\nJSON index:      {cfg.JSON_INDEX}")
    print(f"Conversations:   {cfg.JSON_CONVERSATIONS_DIR}/")
    print("=" * 60 + "\n")


def run_milestone2(stats: dict):
    from . import config

    total = stats.get("total_attachments", 0)
    copied = stats.get("copied", 0)
    skipped = stats.get("skipped_existing", 0)
    missing = stats.get("missing_in_backup", 0)
    not_media = stats.get("not_in_media_domain", 0)
    fallback = stats.get("sha1_fallback", 0)
    errors = stats.get("copy_errors", 0)
    bytes_copied = stats.get("bytes_copied", 0)

    print("=" * 60)
    print("MILESTONE 2 VALIDATION REPORT")
    print("=" * 60)
    print(f"\nTotal attachments in sms.db:  {total}")
    print(f"  Copied to output:           {copied}")
    print(f"  Skipped (already exists):   {skipped}")
    print(f"  Missing in backup:          {missing}")
    print(f"  Not in MediaDomain (temp):  {not_media}")
    print(f"  Resolved via SHA1 fallback: {fallback}")
    print(f"  Copy errors:                {errors}")
    mb = bytes_copied / 1_048_576
    print(f"\nTotal bytes copied:           {mb:.1f} MB")

    failed_mimes = stats.get("failed_mimes", {})
    if failed_mimes:
        print("\n--- MIME types of unresolved attachments ---")
        for mime, count in sorted(failed_mimes.items(), key=lambda x: -x[1]):
            print(f"  {mime:<50s}  {count}")
    else:
        print("\nNo unresolved MIME types.")

    print("\n--- Sample resolved attachments (first image-bearing conversation) ---")
    shown_convs = 0
    for conv in stats.get("conversations_raw", []):
        att_msgs = [m for m in conv["messages"] if any(
            a.get("status") == "copied" for a in m.get("attachments", [])
        )]
        if not att_msgs:
            continue
        print(f"\n  {conv['title']!r} ({len(att_msgs)} messages with attachments)")
        for msg in att_msgs[:3]:
            for att in msg["attachments"]:
                if att.get("status") == "copied":
                    full = config.OUTPUT_ROOT / att["path"]
                    size = full.stat().st_size if full.exists() else -1
                    print(f"    {att['path']}  mime={att['mime_type']}  size={size}B")
        shown_convs += 1
        if shown_convs >= 2:
            break

    print(f"\nAttachments dir: {config.OUTPUT_ATTACHMENTS_DIR}/")
    print("=" * 60 + "\n")
