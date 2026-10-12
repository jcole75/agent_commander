"""Classic Norton Commander retro styling and CSS."""

NC_CSS = """
Screen {
    background: #000080;
    color: #ffffff;
}

#title-bar {
    dock: top;
    height: 1;
    background: #00aaaa;
    color: #000000;
    text-style: bold;
    padding: 0 1;
}

#commander-container {
    height: 1fr;
    layout: horizontal;
}

.pane-container {
    width: 1fr;
    height: 1fr;
    border: double #00aaaa;
    background: #000080;
    padding: 0;
    margin: 0;
}

.pane-container.active-pane {
    border: double #ffffff;
    background: #000088;
}

.pane-header {
    height: 1;
    background: #00aaaa;
    color: #ffffff;
    text-style: bold;
    padding: 0 1;
}

.pane-filter-box {
    height: 1;
    background: #000050;
    color: #ffff55;
    display: none;
}

.pane-filter-box.visible {
    display: block;
}

.pane-table {
    height: 1fr;
    background: #000080;
    color: #ffffff;
}

.pane-status {
    height: 1;
    background: #00aaaa;
    color: #000000;
    padding: 0 1;
}

#function-bar {
    dock: bottom;
    height: 1;
    background: #000000;
    color: #ffffff;
    layout: horizontal;
}

.fn-key {
    background: #000000;
    color: #ffffff;
    margin: 0 1 0 0;
}

.fn-num {
    background: #00aaaa;
    color: #000000;
    text-style: bold;
}

.fn-label {
    background: #000000;
    color: #ffffff;
}

/* Dialog and Modal Styles */
.modal-screen {
    align: center middle;
    background: rgba(0, 0, 0, 0.6);
}

.dialog-box {
    width: 76;
    height: auto;
    max-height: 85%;
    border: double #ffffff;
    background: #0000aa;
    color: #ffffff;
    padding: 1 2;
}

.dialog-title {
    text-align: center;
    text-style: bold;
    color: #ffff55;
    margin-bottom: 1;
}

.dialog-buttons {
    layout: horizontal;
    align: center middle;
    margin-top: 1;
    height: 3;
}

.dialog-buttons Button {
    margin: 0 1;
    min-width: 14;
    background: #00aaaa;
    color: #000000;
    border: none;
}

.dialog-buttons Button:focus {
    background: #ffff55;
    color: #000000;
    text-style: bold;
}

/* Viewer Screen */
#viewer-box {
    width: 90%;
    height: 90%;
    border: double #ffffff;
    background: #000080;
    color: #ffffff;
    padding: 1 2;
}

#viewer-header {
    height: 4;
    background: #000050;
    border-bottom: solid #00aaaa;
    padding: 0 1;
    color: #ffff55;
}

#viewer-scroll {
    height: 1fr;
    overflow-y: scroll;
    padding: 1 0;
}

.message-card {
    height: auto;
    margin-bottom: 1;
    padding: 1;
    border: round #00aaaa;
    background: #000066;
    color: #ffffff;
}

.message-user {
    border: round #55ff55;
    background: #000055;
    color: #ffffff;
}

.message-assistant {
    border: round #55ffff;
    background: #000077;
    color: #ffffff;
}

.message-thinking {
    height: auto;
    border: dashed #ffff55;
    color: #ffffaa;
    background: #000044;
    margin: 1 0;
    padding: 0 1;
}

.tool-badge {
    color: #ffaa55;
    text-style: bold;
}
"""
