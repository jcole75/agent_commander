"""Classic Norton Commander bottom function key bar."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class FunctionBar(Widget):
    """Bottom function key bar showing F1-F10 shortcuts."""

    DEFAULT_CSS = """
    FunctionBar {
        dock: bottom;
        height: 1;
        background: #000000;
        color: #ffffff;
        layout: horizontal;
    }
    """

    KEYS = [
        ("1", "Help"),
        ("2", "Plat"),
        ("3", "View"),
        ("4", "Find"),
        ("5", "Copy"),
        ("6", "Rename"),
        ("7", "Export"),
        ("8", "Archive"),
        ("9", "ArcView"),
        ("10", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        items = []
        for num, label in self.KEYS:
            key_tag = f"F{num}" if num.isdigit() else num
            items.append(
                f"[@click=app.fn_action('{num}')][bold black on #00aaaa] {key_tag} [/][bold white on #000040] {label} [/][/]"
            )
        bar_text = " ".join(items)
        yield Static(bar_text, markup=True)
