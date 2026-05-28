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
