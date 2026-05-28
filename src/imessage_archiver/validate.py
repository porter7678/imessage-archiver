from . import config


def run_full(stats: dict) -> None:
    convs = stats.get("conversations_raw", [])
    total_msgs = stats["total_messages"]

    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)

    # --- Extraction ---
    print(f"\n[1/3] Message extraction")
    print(f"  Conversations:  {stats['total_conversations']}")
    print(f"  Total messages: {total_msgs}")

    print("\n  Message text source:")
    pct = lambda n: f"{n:6d}  ({100*n/total_msgs:.1f}%)" if total_msgs else f"{n:6d}"
    print(f"    text column:      {pct(stats['text_source_text'])}")
    print(f"    attributedBody:   {pct(stats['text_source_attributed'])}")
    print(f"    empty:            {pct(stats['text_source_empty'])}")

    confirmed_blank = stats.get("empty_confirmed_blank", 0)
    both_null = stats.get("empty_both_null", 0)
    system_events = stats["text_source_empty"] - confirmed_blank - both_null
    if confirmed_blank:
        print(f"      ({confirmed_blank} intentional blank sends via attributedBody — ok)")
    if system_events > 0:
        print(f"      ({system_events} system events / group actions — expected)")
    if both_null > 0:
        print(f"\n  *** {both_null} messages have BOTH text and attributedBody NULL")

    unresolved = sorted(stats.get("unresolved_handles", set()))
    print(f"\n  Unresolved handles: {len(unresolved)}")
    for h in unresolved[:10]:
        print(f"    {h}")
    if len(unresolved) > 10:
        print(f"    ... and {len(unresolved) - 10} more")

    # --- Attachments ---
    total_att = stats.get("total_attachments", 0)
    copied = stats.get("copied", 0)
    skipped = stats.get("skipped_existing", 0)
    missing = stats.get("missing_in_backup", 0)
    not_media = stats.get("not_in_media_domain", 0)
    fallback = stats.get("sha1_fallback", 0)
    errors = stats.get("copy_errors", 0)
    bytes_copied = stats.get("bytes_copied", 0)

    print(f"\n[2/3] Attachment resolution")
    skipped_video = stats.get("skipped_video", 0)
    print(f"  Total in sms.db:            {total_att}")
    print(f"    Copied to output:         {copied}")
    print(f"    Skipped (video, by policy):{skipped_video}")
    print(f"    Skipped (already exists): {skipped}")
    print(f"    Missing in backup:        {missing}")
    print(f"    Not in MediaDomain (tmp): {not_media}")
    print(f"    Resolved via SHA1 fallbk: {fallback}")
    print(f"    Copy errors:              {errors}")
    mb = bytes_copied / 1_048_576
    print(f"  Total bytes copied:         {mb:.1f} MB")

    failed_mimes = stats.get("failed_mimes", {})
    if failed_mimes:
        print("\n  Unresolved MIME types:")
        for mime, count in sorted(failed_mimes.items(), key=lambda x: -x[1]):
            print(f"    {mime:<50s}  {count}")

    # --- HTML render ---
    render = stats.get("render", {})
    print(f"\n[3/3] HTML render")
    print(f"  Conversation pages written: {render.get('pages_written', 0)}")
    print(f"  index.html:                 {config.HTML_INDEX}")
    print(f"  Inline media rendered:")
    print(f"    Images:  {render.get('inline_images', 0)}")
    print(f"    Videos:  {render.get('inline_videos', 0)}")
    print(f"    Audio:   {render.get('inline_audio', 0)}")
    print(f"    Other:   {render.get('inline_other', 0)}")
    print(f"  Unavailable attachment placeholders: {render.get('unavailable_attachments', 0)}")

    largest = render.get("largest_page")
    if largest:
        size_kb = largest.stat().st_size // 1024
        print(f"\n  Largest conversation page ({size_kb} KB):")
        print(f"    {largest}")

    # --- Sample messages ---
    print("\n--- Sample messages (first 3 from 2 conversations) ---")
    shown = 0
    for conv in convs:
        if shown >= 2:
            break
        style_label = f"[{conv['style']}]"
        print(f"\n  {style_label} {conv['title']!r}  (chat_id={conv['chat_id']})")
        for msg in conv["messages"][:3]:
            ts = msg.get("timestamp") or "?"
            sender = msg.get("sender_name") or "?"
            text = (msg.get("text") or "").replace("\n", " ")[:120]
            print(f"    {ts}  {sender}: {text!r}")
        shown += 1

    print("\n" + "=" * 60 + "\n")
