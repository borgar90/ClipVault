import argparse
import sys
import time
from datetime import datetime
from typing import List, Optional

import pyperclip

from copyhistory_core import (
    ClipItem,
    add_clip,
    fetch_clips,
    get_clip_by_id,
    get_all_clips,
    delete_all_clips,
)


def monitor_clipboard(poll_interval: float = 0.4) -> None:
    print("Monitoring clipboard. Press Ctrl+C to stop.")
    last_value = None
    initialized = False
    try:
        while True:
            try:
                current = pyperclip.paste()
            except Exception as exc:
                print(f"Error reading clipboard: {exc}", file=sys.stderr)
                time.sleep(poll_interval)
                continue

            if not initialized:
                # Ignore whatever was already on the clipboard when monitoring started
                last_value = current if isinstance(current, str) else None
                initialized = True
            elif current and isinstance(current, str) and current != last_value:
                last_value = current
                item_id = add_clip(current)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Captured new item id={item_id}")

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\nStopped monitoring.")


def cmd_monitor(args: argparse.Namespace) -> None:
    monitor_clipboard(poll_interval=args.interval)


def cmd_list(args: argparse.Namespace) -> None:
    clips = fetch_clips(limit=args.limit, search=args.search)
    if not clips:
        print("No clipboard history yet.")
        return

    for item in clips:
        title = item.title or "(no title yet)"
        category = item.category or "-"
        preview = item.content.replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:77] + "..."
        print(f"[{item.id}] {item.created_at} | {category} | {title}")
        print(f"      {preview}")


def cmd_copy(args: argparse.Namespace) -> None:
    item = get_clip_by_id(args.id)
    if not item:
        print(f"No item with id {args.id}")
        return
    try:
        pyperclip.copy(item.content)
    except Exception as exc:
        print(f"Error writing to clipboard: {exc}", file=sys.stderr)
        return
    print(f"Copied item {item.id} back to clipboard.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simple Windows clipboard history tool."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Monitor the clipboard and store history.",
    )
    monitor_parser.add_argument(
        "--interval",
        type=float,
        default=0.4,
        help="Polling interval in seconds (default: 0.4).",
    )
    monitor_parser.set_defaults(func=cmd_monitor)

    list_parser = subparsers.add_parser(
        "list",
        help="List recent clipboard items.",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of items to show (default: 20).",
    )
    list_parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search text in content, title, or category.",
    )
    list_parser.set_defaults(func=cmd_list)

    copy_parser = subparsers.add_parser(
        "copy",
        help="Copy a stored item back into the clipboard.",
    )
    copy_parser.add_argument("id", type=int, help="ID of the item to copy.")
    copy_parser.set_defaults(func=cmd_copy)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
