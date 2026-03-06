"""Query view widgets for asking repository questions."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class QueryView(QWidget):
    """UI panel that handles natural language queries."""

    def __init__(self) -> None:
        """Initialize query form and answer output widgets."""
        super().__init__()

        self.title_label = QLabel("Consulta")
        self.subtitle_label = QLabel(
            "Haz preguntas sobre el repositorio indexado y revisa la respuesta sintetizada."
        )
        self.status_chip = QLabel("Lista")
        self.status_chip.setObjectName("queryStatusChip")
        self.status_chip.setProperty("state", "idle")

        self.repo_id = QLineEdit()
        self.repo_id.setPlaceholderText("ID del repositorio (ej: mall)")

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Consulta la base de conocimientos...")
        self.query_input.returnPressed.connect(self._trigger_submit)

        self.query_button = QPushButton("↑")
        self.query_button.setFixedWidth(44)

        self.history_container = QWidget()
        self.history_layout = QVBoxLayout()
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(12)
        self.history_layout.addStretch(1)
        self.history_container.setLayout(self.history_layout)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setWidget(self.history_container)
        self.history_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.input_bar = QFrame()
        self.input_bar.setObjectName("inputBar")
        self.input_bar.setProperty("state", "idle")

        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)
        input_layout.addWidget(self.query_input)
        input_layout.addWidget(self.query_button)
        self.input_bar.setLayout(input_layout)

        repo_bar = QHBoxLayout()
        repo_label = QLabel("ID de repositorio")
        repo_bar.addWidget(repo_label)
        repo_bar.addWidget(self.repo_id)

        top_bar = QGridLayout()
        top_bar.addWidget(self.title_label, 0, 0)
        top_bar.addWidget(self.status_chip, 0, 1)
        top_bar.addWidget(self.subtitle_label, 1, 0, 1, 2)

        layout = QVBoxLayout()
        layout.addLayout(top_bar)
        layout.addLayout(repo_bar)
        layout.addWidget(self.history_scroll)
        layout.addWidget(self.input_bar)
        self.setLayout(layout)

        self.append_assistant_message(
            "Listo para auditar. Haz una pregunta para comenzar."
        )

        self.setStyleSheet(
            """
            QWidget {
                font-size: 13px;
            }
            QLabel {
                color: #E5E7EB;
            }
            QueryView {
                background-color: #111827;
            }
            QLabel#queryStatusChip {
                padding: 4px 10px;
                border-radius: 10px;
                font-weight: 600;
                color: #F3F4F6;
                background-color: #4B5563;
                qproperty-alignment: AlignCenter;
            }
            QLabel#queryStatusChip[state="running"] {
                background-color: #1D4ED8;
            }
            QLabel#queryStatusChip[state="success"] {
                background-color: #15803D;
            }
            QLabel#queryStatusChip[state="error"] {
                background-color: #B91C1C;
            }
            QLineEdit {
                background-color: #0F172A;
                color: #E5E7EB;
                border: 1px solid #374151;
                border-radius: 8px;
                padding: 6px;
            }
            QScrollArea {
                background-color: transparent;
            }
            QFrame#inputBar {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 12px;
            }
            QFrame#inputBar[state="running"] {
                border: 1px solid #F59E0B;
                background-color: #1F2937;
            }
            QFrame#inputBar[state="error"] {
                border: 1px solid #B91C1C;
            }
            QFrame#msgUser {
                background-color: #1D4ED8;
                border-radius: 12px;
                padding: 8px;
            }
            QFrame#msgAssistant {
                background-color: #1F2937;
                border: 1px solid #374151;
                border-radius: 12px;
                padding: 8px;
            }
            QFrame#msgError {
                background-color: #3F1D1D;
                border: 1px solid #B91C1C;
                border-radius: 12px;
                padding: 8px;
            }
            QLabel#msgText {
                color: #E5E7EB;
            }
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 9px;
                font-weight: 700;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #CBD5E1;
            }
            """
        )

    def set_status(self, state: str, text: str) -> None:
        """Update query status chip state and text."""
        valid_states = {"idle", "running", "success", "error"}
        selected_state = state if state in valid_states else "idle"
        self.status_chip.setProperty("state", selected_state)
        self.status_chip.setText(text)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

    def set_running(self, running: bool) -> None:
        """Enable and disable controls while query request is in progress."""
        self.repo_id.setDisabled(running)
        self.query_input.setDisabled(running)
        self.query_button.setDisabled(running)
        self.query_button.setText("…" if running else "↑")
        self.input_bar.setProperty("state", "running" if running else "idle")
        self.input_bar.style().unpolish(self.input_bar)
        self.input_bar.style().polish(self.input_bar)

    def get_question_text(self) -> str:
        """Return trimmed question input text."""
        return self.query_input.text().strip()

    def clear_question(self) -> None:
        """Clear query input after successful submission."""
        self.query_input.clear()

    def append_user_message(self, text: str) -> None:
        """Append user question to chat history."""
        self._append_message(text=text, role="user", error=False)

    def append_assistant_message(self, text: str, error: bool = False) -> None:
        """Append assistant response or error to chat history."""
        self._append_message(text=text, role="assistant", error=error)

    def _append_message(self, text: str, role: str, error: bool) -> None:
        """Render a chat bubble aligned by role and keep history visible."""
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        bubble = QFrame()
        bubble_name = "msgUser" if role == "user" else "msgAssistant"
        if error:
            bubble_name = "msgError"
        bubble.setObjectName(bubble_name)

        bubble_layout = QVBoxLayout()
        bubble_layout.setContentsMargins(10, 8, 10, 8)

        text_label = QLabel(text)
        text_label.setObjectName("msgText")
        text_label.setWordWrap(True)
        bubble_layout.addWidget(text_label)
        bubble.setLayout(bubble_layout)

        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)

        row_widget.setLayout(row_layout)
        insert_index = max(0, self.history_layout.count() - 1)
        self.history_layout.insertWidget(insert_index, row_widget)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        """Scroll chat view to latest message."""
        scrollbar = self.history_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _trigger_submit(self) -> None:
        """Trigger query button click from keyboard Enter key."""
        if self.query_button.isEnabled():
            self.query_button.click()
