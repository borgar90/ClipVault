import threading
import time
from datetime import datetime
from typing import Optional, List, Callable

import os
import sys
import tempfile
import getpass
import msvcrt

import tkinter as tk
from tkinter import messagebox, PhotoImage, filedialog
from tkinter import ttk

import csv
import webbrowser

from PIL import Image
import pystray
import pyperclip
import sv_ttk

from copyhistory_core import (
    ClipItem,
    add_clip,
    fetch_clips,
    get_clip_by_id,
    get_all_clips,
    delete_all_clips,
)


# ============================
#   Single-instance guard
# ============================


class SingleInstanceError(RuntimeError):
    """Raised when another ClipVault instance is already running."""


class SingleInstanceLock:
    """Simple single-instance lock based on a per-user lock file."""

    def __init__(self, name: str = "copyhistory_gui.lock") -> None:
        user = getpass.getuser() or "default"
        lock_name = f"{user}_{name}"
        self.lockfile = os.path.join(tempfile.gettempdir(), lock_name)
        # Open (or create) the lock file
        self._fh = open(self.lockfile, "w")
        try:
            # Try to acquire an exclusive, non-blocking lock on 1 byte
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self._fh.close()
            raise SingleInstanceError("Another ClipVault instance is already running.")

    def release(self) -> None:
        try:
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            self._fh.close()
        except Exception:
            pass


def resource_path(relative_path: str) -> str:
    """Return absolute path to resource, works for dev and PyInstaller builds."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ============================
#   Clipboard monitor thread
# ============================


class ClipboardMonitorThread(threading.Thread):
    """Monitors the clipboard in a background thread and stores new text values."""

    def __init__(self, poll_interval: float = 0.4) -> None:
        super().__init__(daemon=True)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._last_value: Optional[str] = None
        # Track whether we've already skipped the initial clipboard content
        self._has_seen_initial_clip: bool = False

    def stop(self) -> None:
        """Stop the monitoring thread safely."""
        self._stop_event.set()

    def run(self) -> None:
        """Main loop that periodically checks the clipboard."""
        while not self._stop_event.is_set():
            try:
                current = pyperclip.paste()
            except Exception:
                time.sleep(self.poll_interval)
                continue

            if not self._has_seen_initial_clip:
                # Ignore whatever was already on the clipboard when the app started
                self._last_value = current if isinstance(current, str) else None
                self._has_seen_initial_clip = True
            elif current and isinstance(current, str) and current != self._last_value:
                self._last_value = current
                add_clip(current)

            time.sleep(self.poll_interval)


# ============================
#   SnippetCard widget
# ============================


class SnippetCard(ttk.Frame):
    """Single card component for one clipboard snippet."""

    def __init__(
        self,
        master,
        item: ClipItem,
        preview_text: str,
        on_select: Callable[[int, "SnippetCard"], None],
        on_copy: Callable[[int], None],
        on_details: Callable[[int], None],
        *args,
        **kwargs,
    ):
        super().__init__(master, *args, style="SnippetCard.TFrame", **kwargs)

        self.item = item
        self.item_id = item.id
        self._on_select = on_select
        self._on_copy = on_copy
        self._on_details = on_details

        self._selected = False

        self.grid_columnconfigure(1, weight=1)

        # Left indicator
        self.indicator = ttk.Label(
            self,
            text="*",
            style="SnippetCard.Indicator.TLabel",
        )
        self.indicator.grid(row=0, column=0, padx=(12, 10), pady=8, sticky="w")

        # Text preview
        self.label = ttk.Label(
            self,
            text=preview_text,
            anchor="w",
            style="SnippetCard.Text.TLabel",
        )
        self.label.grid(row=0, column=1, sticky="w", pady=8)

        # Copy button on the right
        self.copy_button = ttk.Button(
            self,
            text="Copy",
            command=self._copy_click,
            style="Accent.TButton",
        )
        self.copy_button.grid(row=0, column=2, padx=(10, 14), pady=6, sticky="e")

        # Mouse bindings
        self.bind("<Button-1>", self._click)
        self.bind("<Double-Button-1>", self._double_click)

        for widget in (self.label, self.indicator):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Double-Button-1>", self._double_click)

    # ---------- selection handling ----------

    def set_selected(self, value: bool) -> None:
        """Mark this card as selected / not selected and update style."""
        self._selected = value
        if value:
            self.configure(style="SnippetCard.Selected.TFrame")
        else:
            self.configure(style="SnippetCard.TFrame")

    # ---------- event callbacks ----------

    def _click(self, event) -> None:
        self._on_select(self.item_id, self)

    def _double_click(self, event) -> None:
        self._on_details(self.item_id)

    def _copy_click(self) -> None:
        self._on_copy(self.item_id)


# ============================
#   Main application window
# ============================


class CopyHistoryApp(tk.Tk):
    """Main window for ClipVault with Sun Valley light theme."""

    def __init__(self) -> None:
        super().__init__()

        # Apply Sun Valley light theme
        sv_ttk.set_theme("light")

        self.title("ClipVault - Clipboard History")

        # Icon
        self._icon_photo: Optional[PhotoImage]
        try:
            self._icon_photo = PhotoImage(file=resource_path("icon.png"))
            self.iconphoto(False, self._icon_photo)
        except Exception:
            self._icon_photo = None

        # Logo (no longer used in the banner, but kept for possible future use)
        self._logo_photo: Optional[PhotoImage]
        self._logo_small: Optional[PhotoImage]
        try:
            self._logo_photo = PhotoImage(file=resource_path("logo.png"))
            self._logo_small = self._logo_photo.subsample(2, 2)
        except Exception:
            self._logo_photo = self._icon_photo
            self._logo_small = self._icon_photo

        self.geometry("900x600")

        # Clipboard monitor
        self.monitor_thread = ClipboardMonitorThread(poll_interval=0.4)
        self.monitor_thread.start()

        # System tray icon support
        self.tray_icon: Optional[pystray.Icon] = None

        # Single-instance lock (owned by the app for the GUI lifetime)
        self._instance_lock: Optional[SingleInstanceLock] = None

        self.last_selected_id: Optional[int] = None
        self.cards: List[SnippetCard] = []
        self.day_groups: dict[str, dict] = {}
        self._last_clip_ids: List[int] = []
        self._last_search_text: Optional[str] = None
        self.sort_desc: bool = True  # True = newest first
        self._last_sort_desc: bool = True

        # Search placeholder handling
        self._search_placeholder = "Search snippets..."
        self._search_has_placeholder: bool = True

        self._build_menubar()

        self._setup_styles()
        self._build_ui()
        self._refresh_data()
        self._schedule_auto_refresh()

        # Ensure tray icon exists from startup (not only after closing)
        self._ensure_tray_icon()

    def _setup_styles(self) -> None:
        """Configure styles building on top of Sun Valley theme."""
        style = ttk.Style(self)

        base_bg = style.lookup("TFrame", "background") or "#ffffff"

        # Background for snippet area behind cards
        container_bg = "#e9edf5"
        self._snippet_container_bg = container_bg
        style.configure(
            "SnippetContainer.TFrame",
            background=container_bg,
        )

        # Card backgrounds and borders for clearer separation
        card_bg = "#ffffff"
        card_selected_bg = "#e0ecff"
        style.configure(
            "SnippetCard.TFrame",
            padding=10,
            relief="flat",
            borderwidth=1,
            background=card_bg,
        )
        style.configure(
            "SnippetCard.Selected.TFrame",
            padding=10,
            relief="solid",
            borderwidth=1,
            background=card_selected_bg,
        )

        accent_fg = style.lookup("Accent.TButton", "foreground") or style.lookup(
            "TButton", "foreground"
        )
        style.configure(
            "SnippetCard.Indicator.TLabel",
            foreground=accent_fg,
            background=card_bg,
        )
        style.configure("SnippetCard.Text.TLabel", background=card_bg)

        # Slightly higher-contrast search field
        style.configure(
            "Search.TEntry",
            fieldbackground="#f3f3f3",
        )

        # Day header labels for grouping per local date
        style.configure(
            "DayHeader.TLabel",
            font=("Segoe UI", 10, "bold"),
            foreground="#33415c",
            background="#d1d8eb",
            padding=(6, 3),
        )

    # ---------- layout ----------

    def _build_menubar(self) -> None:
        """Create the main application menubar."""
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Export all snippets...",
            command=self._export_all_snippets,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Delete all snippets...",
            command=self._delete_all_snippets,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Quit",
            command=self._quit_app,
        )
        menubar.add_cascade(label="File", menu=file_menu)

        about_menu = tk.Menu(menubar, tearoff=False)
        about_menu.add_command(
            label="About ClipVault...",
            command=self._show_about_dialog,
        )
        menubar.add_cascade(label="About", menu=about_menu)

        self.config(menu=menubar)

    def _build_ui(self) -> None:
        """Builds the full GUI layout."""
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Logo row (centered above search/filter)
        logo_frame = ttk.Frame(self, padding=(0, 12, 0, 0))
        logo_frame.grid(row=0, column=0, sticky="ew")
        logo_frame.grid_columnconfigure(0, weight=1)
        if self._logo_small is not None:
            logo_label = ttk.Label(logo_frame, image=self._logo_small, text="")
            logo_label.grid(row=0, column=0, pady=(0, 4))

        # Top banner: search field + sort toggle
        top_frame = ttk.Frame(self, padding=(16, 12, 16, 6))
        top_frame.grid(row=1, column=0, sticky="ew")
        top_frame.grid_columnconfigure(0, weight=1)
        top_frame.grid_columnconfigure(1, weight=0)

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(
            top_frame,
            textvariable=self.search_var,
            style="Search.TEntry",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.search_entry.bind("<Return>", lambda event: self._refresh_data())
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)

        # Initialize placeholder
        self.search_var.set(self._search_placeholder)
        self.search_entry.configure(foreground="#8a8a8a")

        # Sort toggle button (asc/desc by date)
        self.sort_button = ttk.Button(
            top_frame,
            width=12,
            command=self._toggle_sort_order,
        )
        self._update_sort_button_label()
        self.sort_button.grid(row=0, column=1, padx=(8, 0), pady=(0, 4), sticky="e")

        section_label = ttk.Label(
            top_frame,
            text="Snippet History",
            font=("Segoe UI", 16, "bold"),
        )
        section_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Center area: scrollable list of cards
        center_frame = ttk.Frame(self, padding=(14, 0, 14, 6))
        center_frame.grid(row=2, column=0, sticky="nsew")
        center_frame.grid_rowconfigure(0, weight=1)
        center_frame.grid_columnconfigure(0, weight=1)

        self.snippet_canvas = tk.Canvas(center_frame, highlightthickness=0)
        canvas_bg = getattr(
            self,
            "_snippet_container_bg",
            ttk.Style(self).lookup("TFrame", "background") or "#ffffff",
        )
        self.snippet_canvas.configure(background=canvas_bg)
        self.snippet_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            center_frame, orient="vertical", command=self.snippet_canvas.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.snippet_canvas.configure(yscrollcommand=scrollbar.set)

        self.snippet_scroll = ttk.Frame(
            self.snippet_canvas,
            style="SnippetContainer.TFrame",
        )
        self._snippet_window_id = self.snippet_canvas.create_window(
            (0, 0), window=self.snippet_scroll, anchor="nw"
        )

        self.snippet_scroll.bind(
            "<Configure>",
            lambda event: self.snippet_canvas.configure(
                scrollregion=self.snippet_canvas.bbox("all")
            ),
        )
        self.snippet_canvas.bind("<Configure>", self._on_snippet_canvas_configure)

        self.snippet_scroll.grid_columnconfigure(0, weight=1)

        # Bottom status bar
        bottom_frame = ttk.Frame(self, padding=(16, 0, 16, 12))
        bottom_frame.grid(row=3, column=0, sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ttk.Label(
            bottom_frame,
            text="Ready",
            anchor="w",
            font=("Segoe UI", 11),
        )
        self.status_label.grid(row=0, column=0, padx=4, pady=6, sticky="w")

    def _on_snippet_canvas_configure(self, event: tk.Event) -> None:
        """Keep cards as wide as the canvas."""
        self.snippet_canvas.itemconfigure(self._snippet_window_id, width=event.width)

    # ---------- auto refresh ----------

    def _schedule_auto_refresh(self) -> None:
        """Schedule periodic refresh of the list view."""
        self.after(3000, self._auto_refresh_callback)

    def _auto_refresh_callback(self) -> None:
        self._refresh_data()
        self._schedule_auto_refresh()

    # ---------- data loading / view ----------

    def _clear_cards(self) -> None:
        # Destroy all widgets inside the scroll frame (cards + headers)
        for child in self.snippet_scroll.winfo_children():
            child.destroy()
        self.cards.clear()
        self.day_groups.clear()

    def _export_all_snippets(self) -> None:
        """Export all snippets to a CSV file."""
        path = filedialog.asksaveasfilename(
            title="Export snippets to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            clips = get_all_clips()
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "created_at", "title", "category", "content"])
                for item in clips:
                    writer.writerow(
                        [item.id, item.created_at, item.title, item.category, item.content]
                    )
        except Exception as exc:
            messagebox.showerror(
                "Export error",
                f"Could not export snippets:\n{exc}",
            )
            return

        messagebox.showinfo(
            "Export completed",
            f"Exported {len(clips)} snippets to:\n{path}",
        )

    def _delete_all_snippets(self) -> None:
        """Delete all snippets after user confirmation."""
        if not messagebox.askyesno(
            "Delete all snippets",
            "This will permanently delete all snippets from the history.\n\n"
            "Are you sure you want to continue?",
        ):
            return

        try:
            count = delete_all_clips()
        except Exception as exc:
            messagebox.showerror(
                "Delete error",
                f"Could not delete snippets:\n{exc}",
            )
            return

        self._last_clip_ids = []
        self._refresh_data(force=True)

        messagebox.showinfo(
            "Delete completed",
            f"Deleted {count} snippet(s) from the history.",
        )

    def _show_about_dialog(self) -> None:
        """Show an About dialog with logo, link and short intro."""
        about = tk.Toplevel(self)
        about.title("About ClipVault")
        about.geometry("380x260")
        if self._icon_photo is not None:
            about.iconphoto(False, self._icon_photo)
        about.transient(self)
        about.grab_set()

        content = ttk.Frame(about, padding=16)
        content.pack(fill="both", expand=True)
        content.grid_columnconfigure(0, weight=1)

        if self._logo_small is not None:
            logo_label = ttk.Label(content, image=self._logo_small, text="")
            logo_label.grid(row=0, column=0, pady=(0, 8))

        title_label = ttk.Label(
            content,
            text="ClipVault",
            font=("Segoe UI", 14, "bold"),
        )
        title_label.grid(row=1, column=0, pady=(0, 4))

        intro_text = (
            "ClipVault is a simple clipboard\n"
            "history tool created by\n"
            "Borgar Flaen Stensrud."
        )
        intro_label = ttk.Label(
            content,
            text=intro_text,
            justify="center",
        )
        intro_label.grid(row=2, column=0, pady=(0, 8))

        link_label = ttk.Label(
            content,
            text="borgar-stensrud.no",
            foreground="#0066cc",
            cursor="hand2",
        )
        link_label.grid(row=3, column=0, pady=(0, 10))
        link_label.bind(
            "<Button-1>", lambda event: webbrowser.open("https://borgar-stensrud.no/")
        )

        close_button = ttk.Button(
            content,
            text="Close",
            command=about.destroy,
            width=10,
        )
        close_button.grid(row=4, column=0, pady=(4, 0))

    def _on_search_focus_in(self, event: tk.Event) -> None:
        """Clear placeholder text when search field gains focus."""
        if self._search_has_placeholder:
            self.search_var.set("")
            # Reset to default foreground (None lets the style decide)
            self.search_entry.configure(foreground="")
            self._search_has_placeholder = False

    def _on_search_focus_out(self, event: tk.Event) -> None:
        """Restore placeholder text if search field is empty."""
        if not self.search_var.get().strip():
            self._search_has_placeholder = True
            self.search_var.set(self._search_placeholder)
            self.search_entry.configure(foreground="#8a8a8a")

    def _update_sort_button_label(self) -> None:
        """Update text on the sort toggle button."""
        if not hasattr(self, "sort_button"):
            return
        if self.sort_desc:
            self.sort_button.configure(text="Newest ↓")
        else:
            self.sort_button.configure(text="Oldest ↑")

    def _toggle_sort_order(self) -> None:
        """Toggle between ascending and descending sort by date."""
        self.sort_desc = not self.sort_desc
        self._update_sort_button_label()
        # Force refresh to apply new sort order
        self._refresh_data()

    def _local_date_str(self, created_at: Optional[str]) -> str:
        """Return local-date string (YYYY-MM-DD) from stored UTC timestamp."""
        if not created_at:
            return "Unknown date"
        try:
            ts = created_at.strip()
            if ts.endswith("Z"):
                ts = ts.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(ts)
            local_date = dt_utc.astimezone().date()
            return local_date.isoformat()
        except Exception:
            # Fallback: just take the date part if present
            return (created_at.split("T", 1)[0] or "Unknown date")

    def _refresh_data(self, force: bool = False) -> None:
        """Fetch clips from the database and build cards."""
        raw_search = self.search_var.get()
        if self._search_has_placeholder:
            search_text = None
        else:
            search_text = raw_search.strip() or None
        clips = fetch_clips(limit=200, search=search_text)
        new_ids = [item.id for item in clips]

        # Avoid rebuilding UI (and flashing) if data didn't change
        if (
            not force
            and new_ids == self._last_clip_ids
            and search_text == self._last_search_text
            and self.sort_desc == self._last_sort_desc
        ):
            self.status_label.configure(
                text=f"Showing {len(clips)} item(s)"
                + (f" for search '{search_text}'" if search_text else "")
            )
            return

        self._last_clip_ids = new_ids
        self._last_search_text = search_text
        self._last_sort_desc = self.sort_desc

        self._clear_cards()
        current_date_label: Optional[str] = None
        row_index = 0

        # Sort items by local datetime according to current sort order
        def sort_key(clip: ClipItem) -> datetime:
            ts = (clip.created_at or "").strip()
            try:
                if ts.endswith("Z"):
                    ts = ts.replace("Z", "+00:00")
                dt_utc = datetime.fromisoformat(ts)
                return dt_utc.astimezone()
            except Exception:
                return datetime.min

        clips_sorted = sorted(clips, key=sort_key, reverse=self.sort_desc)

        for item in clips_sorted:
            # Group by local calendar date
            date_str = self._local_date_str(item.created_at)
            if date_str != current_date_label:
                header = ttk.Label(
                    self.snippet_scroll,
                    text=f"▼ {date_str}",
                    style="DayHeader.TLabel",
                )
                header.grid(
                    row=row_index,
                    column=0,
                    sticky="w",
                    padx=8,
                    pady=(8, 2),
                )
                self.day_groups[date_str] = {
                    "header": header,
                    "cards": [],
                    "expanded": True,
                }
                header.bind(
                    "<Button-1>",
                    lambda event, d=date_str: self._toggle_day_group(d),
                )
                current_date_label = date_str
                row_index += 1

            preview = item.content.replace("\n", " ")
            if len(preview) > 90:
                preview = preview[:87] + "..."

            card = SnippetCard(
                self.snippet_scroll,
                item=item,
                preview_text=preview,
                on_select=self._on_card_selected,
                on_copy=self._copy_item_to_clipboard,
                on_details=self._show_item_details,
            )

            card.grid(
                row=row_index,
                column=0,
                sticky="ew",
                padx=10,
                pady=(4, 6),
            )
            self.cards.append(card)
            self.day_groups[date_str]["cards"].append(card)
            row_index += 1

        # Update visual selection state on cards
        for card in self.cards:
            card.set_selected(card.item_id == self.last_selected_id)

        self.status_label.configure(
            text=f"Showing {len(clips)} item(s)"
            + (f" for search '{search_text}'" if search_text else "")
        )

    def _toggle_day_group(self, date_str: str) -> None:
        """Toggle expand/collapse for a given date group."""
        group = self.day_groups.get(date_str)
        if not group:
            return

        if group["expanded"]:
            for card in group["cards"]:
                card.grid_remove()
            group["expanded"] = False
            group["header"].configure(text=f"▶ {date_str}")
        else:
            for card in group["cards"]:
                card.grid()
            group["expanded"] = True
            group["header"].configure(text=f"▼ {date_str}")

    # ---------- card interaction ----------

    def _on_card_selected(self, item_id: int, card: SnippetCard) -> None:
        self.last_selected_id = item_id
        for c in self.cards:
            c.set_selected(c is card)

    # ---------- copy ----------

    def _copy_selected(self) -> None:
        if not self.last_selected_id:
            messagebox.showinfo("ClipVault", "Click a snippet card first.")
            return
        self._copy_item_to_clipboard(self.last_selected_id)

    def _copy_item_to_clipboard(self, item_id: int) -> None:
        item: Optional[ClipItem] = get_clip_by_id(item_id)
        if not item:
            messagebox.showerror("ClipVault", f"Item with id {item_id} not found.")
            return

        try:
            pyperclip.copy(item.content)
        except Exception as exc:
            messagebox.showerror("ClipVault", f"Error writing to clipboard:\n{exc}")
            return

        self.status_label.configure(text=f"Copied item {item.id} to clipboard.")

    # ---------- detail view ----------

    def _show_item_details(self, item_id: int) -> None:
        item: Optional[ClipItem] = get_clip_by_id(item_id)
        if not item:
            messagebox.showerror("ClipVault", f"Item with id {item_id} not found.")
            return

        detail_window = tk.Toplevel(self)
        detail_window.title(f"Clipboard item {item.id}")
        detail_window.geometry("600x400")
        if self._icon_photo is not None:
            detail_window.iconphoto(False, self._icon_photo)
        detail_window.transient(self)
        detail_window.grab_set()

        header_text = f"ID: {item.id}  |  Time: {item.created_at}"
        header_label = ttk.Label(
            detail_window,
            text=header_text,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        header_label.pack(fill="x", padx=10, pady=(10, 4))

        text_frame = ttk.Frame(detail_window)
        text_frame.pack(fill="both", expand=True, padx=10, pady=6)

        text_box = tk.Text(text_frame, wrap="word")
        text_box.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=text_box.yview,
        )
        scrollbar.pack(side="right", fill="y")
        text_box.configure(yscrollcommand=scrollbar.set)

        text_box.insert("1.0", item.content)
        text_box.configure(state="disabled")

        close_button = ttk.Button(
            detail_window,
            text="Close",
            command=detail_window.destroy,
            width=10,
        )
        close_button.pack(pady=(4, 10))

    # ---------- shutdown ----------

    def on_close(self) -> None:
        # Close button (X): hide window and keep logging in background tray icon
        self.withdraw()
        self._ensure_tray_icon()

    def _ensure_tray_icon(self) -> None:
        """Create and start the system tray icon if not already running."""
        if self.tray_icon is not None:
            return

        # Try to load icon image for tray
        try:
            tray_image = Image.open(resource_path("icon.png"))
        except Exception:
            # Fallback: simple 16x16 blank image
            tray_image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

        menu = pystray.Menu(
            pystray.MenuItem("Show ClipVault", self._tray_show),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        self.tray_icon = pystray.Icon("ClipVault", tray_image, "ClipVault", menu)

        def run_tray() -> None:
            self.tray_icon.run()

        threading.Thread(target=run_tray, daemon=True).start()

    def _tray_show(self, icon: pystray.Icon, item) -> None:
        """Callback from tray icon to show the main window."""
        # Must interact with Tk on the main thread
        self.after(0, self._show_main_window)

    def _show_main_window(self) -> None:
        """Show and raise the main window."""
        self.deiconify()
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _tray_quit(self, icon: pystray.Icon, item) -> None:
        """Callback from tray icon to quit the app."""
        # Schedule quitting on Tk main thread
        self.after(0, self._quit_app)

    def _quit_app(self) -> None:
        """Quit the application and stop monitoring + tray icon."""
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

        if self.monitor_thread.is_alive():
            self.monitor_thread.stop()

        # Release single-instance lock if owned
        if self._instance_lock is not None:
            try:
                self._instance_lock.release()
            except Exception:
                pass
            self._instance_lock = None

        self.destroy()


# ============================
#   main()
# ============================


def main() -> None:
    # Enforce single-instance per user for the GUI
    try:
        instance_lock = SingleInstanceLock()
    except SingleInstanceError:
        # Optional: print a message; UI feedback is tricky without another Tk root
        print("ClipVault GUI is already running for this user.", file=sys.stderr)
        return

    app = CopyHistoryApp()
    # Attach lock to app so it can be released on clean quit
    app._instance_lock = instance_lock
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
