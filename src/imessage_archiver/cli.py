from . import copy_dbs, extract, render, validate


def main() -> None:
    print("=== iMessage Archiver ===\n")

    print("Step 1: Copying databases to scratch dir...")
    copy_dbs.run()

    print("\nStep 2: Extracting messages and resolving attachments...")
    stats = extract.run()
    print(f"  Done — {stats['total_conversations']} conversations, {stats['total_messages']} messages")
    print(f"  Attachments: {stats['copied']} copied, {stats['skipped_existing']} skipped, "
          f"{stats['missing_in_backup']} missing")

    print("\nStep 3: Rendering HTML archive...")
    render_stats = render.run()
    stats["render"] = render_stats
    print(f"  Done — {render_stats['pages_written']} conversation pages written")

    validate.run_full(stats)


if __name__ == "__main__":
    main()
