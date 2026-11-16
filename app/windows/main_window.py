

from __future__ import annotations

from datetime import datetime
import json

from PySide6.QtCore import QEvent, QSize, QThread, QTimer, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.exceptions import (
    CityNotFoundError,
    ConnectionServiceError,
    HttpStatusServiceError,
    InvalidJsonServiceError,
    InvalidResponseServiceError,
    InputValidationError,
    RequestServiceError,
    TimeoutServiceError,
)
from app.services.registro_services import RegistroResult
from app.services.weather_services import WeatherData
from app.workers import RegistroWorker, WeatherWorker


class BackgroundWidget(QWidget):
    """Pinta la imagen de fondo a modo de cover, sin deformarla."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._background = QPixmap(":/images/fondoimg.jpg")

    def paintEvent(self, event) -> None:  
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if not self._background.isNull():
            scaled = self._background.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        painter.fillRect(self.rect(), QColor(5, 18, 30, 30))
        painter.end()


class PostSuccessDialog(QDialog):
    def __init__(self, result: RegistroResult, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("postSuccessDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(590, 500)
        self.setMinimumSize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("POST realizado con éxito", self)
        title.setObjectName("postSuccessTitle")
        header.addWidget(title)
        header.addStretch(1)

        close_button = QPushButton("×", self)
        close_button.setObjectName("postDialogCloseButton")
        close_button.setAccessibleName("Cerrar resultado del POST")
        close_button.setToolTip("Cerrar")
        close_button.setFixedSize(34, 34)
        close_button.clicked.connect(self.accept)
        header.addWidget(close_button)
        layout.addLayout(header)

        description = QLabel(
            f"HTTP {result.status_code} · ID {result.record_id}",
            self,
        )
        description.setObjectName("postSuccessDescription")
        layout.addWidget(description)

        json_container = QFrame(self)
        json_container.setObjectName("postJsonContainer")
        json_layout = QVBoxLayout(json_container)
        json_layout.setContentsMargins(1, 1, 1, 1)

        payload = {
            "sent": {
                "city": result.city,
                "temperature_c": result.temperature_c,
                "observation": result.observation,
            },
            "response": result.response_data,
        }
        self.json_text = QPlainTextEdit(json_container)
        self.json_text.setObjectName("postJsonText")
        self.json_text.setReadOnly(True)
        self.json_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.json_text.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.json_text.setPlainText(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
        json_layout.addWidget(self.json_text)
        layout.addWidget(json_container, 1)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - API Qt
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is None:
            return
        center = parent.mapToGlobal(parent.rect().center())
        self.move(
            center.x() - self.width() // 2,
            center.y() - self.height() // 2,
        )


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("mainWindow")
        self.setWindowTitle("Proyecto Clima REST Python")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(1240, 720)
        self.setMinimumSize(940, 600)

        self.current_weather: WeatherData | None = None
        self._weather_thread: QThread | None = None
        self._weather_worker: WeatherWorker | None = None
        self._registro_thread: QThread | None = None
        self._registro_worker: RegistroWorker | None = None
        self._post_success_dialog: PostSuccessDialog | None = None
        self._post_modal_overlay: QWidget | None = None
        self._post_modal_blur: QGraphicsBlurEffect | None = None
        self._close_requested = False

        self._build_ui()
        self._set_initial_state()
        self._connect_actions()
        self._configure_tab_order()

    # ------------------------------------------------------------------
    # Construcción general
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.central_widget = BackgroundWidget(self)
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)

        root_layout = QVBoxLayout(self.central_widget)
        root_layout.setObjectName("rootLayout")
        root_layout.setContentsMargins(14, 12, 14, 12)
        root_layout.setSpacing(0)

        self.main_scroll = QScrollArea(self.central_widget)
        self.main_scroll.setObjectName("mainScrollArea")
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.viewport().setObjectName("scrollViewport")
        self.main_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.main_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        root_layout.addWidget(self.main_scroll)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scrollContent")
        self.scroll_content.setMinimumHeight(800)
        self.main_scroll.setWidget(self.scroll_content)

        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setObjectName("scrollContentLayout")
        scroll_layout.setContentsMargins(20, 16, 20, 18)
        scroll_layout.setSpacing(0)

        self.app_shell = QFrame(self.scroll_content)
        self.app_shell.setObjectName("appShell")
        self.app_shell.setMinimumWidth(900)
        self.app_shell.setMinimumHeight(765)
        self.app_shell.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        scroll_layout.addWidget(self.app_shell)

        shadow = QGraphicsDropShadowEffect(self.app_shell)
        shadow.setBlurRadius(46)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.app_shell.setGraphicsEffect(shadow)
        self._shell_shadow = shadow

        self.shell_layout = QVBoxLayout(self.app_shell)
        self.shell_layout.setObjectName("shellLayout")
        self.shell_layout.setContentsMargins(22, 18, 22, 18)
        self.shell_layout.setSpacing(14)

        self.shell_layout.addWidget(self._build_title_bar())
        self.shell_layout.addWidget(self._build_search_panel())

        content_widget = QWidget(self.app_shell)
        content_widget.setObjectName("contentWidget")
        content_widget.setMinimumHeight(400)
        content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        content_widget.setLayout(self._build_content_layout())
        self.shell_layout.addWidget(content_widget, 1)

        self.shell_layout.addWidget(self._build_footer_panel())

    # ------------------------------------------------------------------
    # Cabecera
    # ------------------------------------------------------------------
    def _build_title_bar(self) -> QWidget:
        self.title_bar = QWidget(self.app_shell)
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(68)

        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(22, 8, 22, 8)
        layout.setSpacing(14)

        self.brand_icon = QLabel(self.title_bar)
        self.brand_icon.setObjectName("brandIcon")
        self.brand_icon.setFixedSize(48, 48)
        self.brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_label_pixmap(
            self.brand_icon,
            ":/weather/mostly-clear-day.svg",
            QSize(46, 46),
        )
        layout.addWidget(self.brand_icon)

        self.title_separator = self._vertical_separator("titleSeparator")
        self.title_separator.setFixedHeight(36)
        layout.addWidget(self.title_separator)

        self.app_title = QLabel("Proyecto Clima REST", self.title_bar)
        self.app_title.setObjectName("appTitle")
        self.app_title.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(self.app_title)
        layout.addStretch(1)

        self._title_drag_targets = (
            self.title_bar,
            self.brand_icon,
            self.title_separator,
            self.app_title,
        )
        for target in self._title_drag_targets:
            target.installEventFilter(self)

        return self.title_bar

    # ------------------------------------------------------------------
    # Buscador
    # ------------------------------------------------------------------
    def _build_search_panel(self) -> QFrame:
        self.search_panel = QFrame(self.app_shell)
        self.search_panel.setObjectName("searchPanel")
        self.search_panel.setMinimumHeight(112)

        layout = QVBoxLayout(self.search_panel)
        layout.setContentsMargins(26, 14, 26, 16)
        layout.setSpacing(9)

        self.search_caption = QLabel("CONSULTAR UBICACIÓN", self.search_panel)
        self.search_caption.setObjectName("searchCaption")
        layout.addWidget(self.search_caption)

        search_row = QHBoxLayout()
        search_row.setObjectName("searchRow")
        search_row.setSpacing(14)

        self.location_input = QLineEdit(self.search_panel)
        self.location_input.setObjectName("locationInput")
        self.location_input.setPlaceholderText("Escribe una ciudad...")
        self.location_input.setText("León, Nicaragua")
        self.location_input.setClearButtonEnabled(False)
        self.location_input.setFixedHeight(54)
        search_row.addWidget(self.location_input, 1)

        self.search_button = QPushButton(self.search_panel)
        self.search_button.setObjectName("searchButton")
        self.search_button.setAccessibleName("Buscar ubicación")
        self.search_button.setToolTip("Buscar ubicación")
        self.search_button.setIcon(QIcon(":/icons/search-02.svg"))
        self.search_button.setIconSize(QSize(27, 27))
        self.search_button.setFixedSize(64, 54)
        search_row.addWidget(self.search_button)

        layout.addLayout(search_row)
        return self.search_panel

    # ------------------------------------------------------------------
    # Contenido principal
    # ------------------------------------------------------------------
    def _build_content_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setObjectName("contentLayout")
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.weather_card = self._build_weather_card()
        self.post_card = self._build_post_card()

        layout.addWidget(self.weather_card, 3)
        layout.addWidget(self.post_card, 2)
        return layout

    def _build_weather_card(self) -> QFrame:
        card = QFrame(self.app_shell)
        card.setObjectName("weatherCard")
        card.setMinimumHeight(400)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(5)

        self.weather_eyebrow = QLabel("CLIMA ACTUAL", card)
        self.weather_eyebrow.setObjectName("weatherEyebrow")
        layout.addWidget(self.weather_eyebrow)

        self.city_label = QLabel("León, Nicaragua", card)
        self.city_label.setObjectName("cityLabel")
        layout.addWidget(self.city_label)

        self.current_conditions_label = QLabel("Condiciones actuales", card)
        self.current_conditions_label.setObjectName("currentConditionsLabel")
        layout.addWidget(self.current_conditions_label)

        layout.addSpacing(8)

        current_weather_widget = QWidget(card)
        current_weather_widget.setObjectName("currentWeatherWidget")
        current_weather_widget.setMinimumHeight(108)
        current_weather_row = QHBoxLayout(current_weather_widget)
        current_weather_row.setContentsMargins(0, 0, 0, 0)
        current_weather_row.setSpacing(18)

        self.weather_icon = QLabel(current_weather_widget)
        self.weather_icon.setObjectName("weatherIcon")
        self.weather_icon.setFixedSize(104, 96)
        self.weather_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_label_pixmap(
            self.weather_icon,
            ":/weather/clear-day.svg",
            QSize(88, 88),
        )
        current_weather_row.addWidget(self.weather_icon)

        weather_separator = self._vertical_separator("weatherMainSeparator")
        weather_separator.setFixedHeight(82)
        current_weather_row.addWidget(weather_separator)

        temperature_block = QVBoxLayout()
        temperature_block.setObjectName("temperatureBlock")
        temperature_block.setContentsMargins(0, 4, 0, 4)
        temperature_block.setSpacing(0)

        self.temperature_label = QLabel("27.7 °C", current_weather_widget)
        self.temperature_label.setObjectName("temperatureLabel")
        self.temperature_label.setMinimumHeight(54)
        self.temperature_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        temperature_block.addWidget(self.temperature_label)

        self.condition_label = QLabel("Despejado", current_weather_widget)
        self.condition_label.setObjectName("conditionLabel")
        self.condition_label.setMinimumHeight(30)
        self.condition_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        temperature_block.addWidget(self.condition_label)
        temperature_block.addStretch(1)

        current_weather_row.addLayout(temperature_block, 1)
        layout.addWidget(current_weather_widget)

        layout.addSpacing(5)
        layout.addWidget(self._horizontal_separator("weatherMetricsSeparator"))
        layout.addSpacing(5)

        metrics_widget = QWidget(card)
        metrics_widget.setObjectName("weatherMetricsWidget")
        metrics_widget.setMinimumHeight(104)
        metrics_layout = QHBoxLayout(metrics_widget)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(0)

        self.humidity_metric, self.humidity_value = self._build_metric(
            parent=metrics_widget,
            object_name="humidityMetric",
            icon_path=":/icons/rain-drop.svg",
            title="Humedad",
            value="89%",
        )
        metrics_layout.addWidget(self.humidity_metric, 1)

        sep_one = self._vertical_separator("metricSeparatorOne")
        sep_one.setFixedHeight(82)
        metrics_layout.addWidget(sep_one)

        self.wind_metric, self.wind_value = self._build_metric(
            parent=metrics_widget,
            object_name="windMetric",
            icon_path=":/icons/wind.svg",
            title="Viento",
            value="12.5 km/h",
        )
        metrics_layout.addWidget(self.wind_metric, 1)

        sep_two = self._vertical_separator("metricSeparatorTwo")
        sep_two.setFixedHeight(82)
        metrics_layout.addWidget(sep_two)

        self.observation_metric, self.observation_time_value = self._build_metric(
            parent=metrics_widget,
            object_name="observationMetric",
            icon_path=":/icons/clock-hour-3.svg",
            title="Observación",
            value="18:15",
        )
        metrics_layout.addWidget(self.observation_metric, 1)
        layout.addWidget(metrics_widget)

        layout.addSpacing(4)
        layout.addWidget(self._horizontal_separator("weatherCoordinatesSeparator"))
        layout.addSpacing(3)

        coordinates_widget = QWidget(card)
        coordinates_widget.setObjectName("coordinatesWidget")
        coordinates_widget.setMinimumHeight(28)
        coordinates_row = QHBoxLayout(coordinates_widget)
        coordinates_row.setContentsMargins(0, 0, 0, 0)
        coordinates_row.setSpacing(9)

        self.coordinates_icon = QLabel(coordinates_widget)
        self.coordinates_icon.setObjectName("coordinatesIcon")
        self.coordinates_icon.setFixedSize(22, 22)
        self._set_label_pixmap(
            self.coordinates_icon,
            ":/icons/location-06.svg",
            QSize(19, 19),
        )
        coordinates_row.addWidget(self.coordinates_icon)

        self.coordinates_label = QLabel(
            "12.4379° N · -86.8780° O",
            coordinates_widget,
        )
        self.coordinates_label.setObjectName("coordinatesLabel")
        coordinates_row.addWidget(self.coordinates_label)
        coordinates_row.addStretch(1)
        layout.addWidget(coordinates_widget)

        return card

    def _build_post_card(self) -> QFrame:
        card = QFrame(self.app_shell)
        card.setObjectName("postCard")
        card.setMinimumHeight(400)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 20, 26, 18)
        layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setObjectName("postTopRow")
        top_row.setSpacing(8)

        self.post_eyebrow = QLabel("POST", card)
        self.post_eyebrow.setObjectName("postEyebrow")
        top_row.addWidget(self.post_eyebrow)
        top_row.addStretch(1)

        self.api_badge = QLabel("API", card)
        self.api_badge.setObjectName("apiBadge")
        self.api_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.api_badge.setFixedSize(58, 30)
        top_row.addWidget(self.api_badge)
        layout.addLayout(top_row)

        self.post_title = QLabel("Registrar observación", card)
        self.post_title.setObjectName("postTitle")
        self.post_title.setMinimumHeight(34)
        layout.addWidget(self.post_title)

        self.post_city_label = QLabel("Ciudad: León", card)
        self.post_city_label.setObjectName("postCityLabel")
        layout.addWidget(self.post_city_label)

        self.post_temperature_label = QLabel("Temperatura: 27.7 °C", card)
        self.post_temperature_label.setObjectName("postTemperatureLabel")
        layout.addWidget(self.post_temperature_label)

        layout.addSpacing(6)
        layout.addWidget(self._horizontal_separator("postSeparator"))
        layout.addSpacing(6)

        self.observation_label = QLabel("Observación", card)
        self.observation_label.setObjectName("observationLabel")
        layout.addWidget(self.observation_label)

        self.observation_input = QPlainTextEdit(card)
        self.observation_input.setObjectName("observationInput")
        self.observation_input.setPlaceholderText("Escribe una observación...")
        self.observation_input.setMinimumHeight(126)
        self.observation_input.setMaximumBlockCount(20)
        layout.addWidget(self.observation_input, 1)

        layout.addSpacing(7)

        self.submit_button = QPushButton("Enviar registro", card)
        self.submit_button.setObjectName("submitButton")
        self.submit_button.setIcon(QIcon(":/icons/cloud-lightning.svg"))
        self.submit_button.setIconSize(QSize(22, 22))
        self.submit_button.setFixedHeight(52)
        layout.addWidget(self.submit_button)

        self.request_state = QWidget(card)
        self.request_state.setObjectName("requestState")
        self.request_state.setMinimumHeight(28)
        request_layout = QHBoxLayout(self.request_state)
        request_layout.setContentsMargins(2, 4, 0, 0)
        request_layout.setSpacing(5)

        for index, name in enumerate(
            ("requestDotOne", "requestDotTwo", "requestDotThree")
        ):
            dot = QLabel("●", self.request_state)
            dot.setObjectName(name)
            request_layout.addWidget(dot)
            if index == 0:
                self.request_dot_one = dot
            elif index == 1:
                self.request_dot_two = dot
            else:
                self.request_dot_three = dot

        request_layout.addSpacing(8)
        self.request_status_label = QLabel(
            "Esperando respuesta...",
            self.request_state,
        )
        self.request_status_label.setObjectName("requestStatusLabel")
        request_layout.addWidget(self.request_status_label)
        request_layout.addStretch(1)
        layout.addWidget(self.request_state)

        return card

    # ------------------------------------------------------------------
    # Footer de servicios
    # ------------------------------------------------------------------
    def _build_footer_panel(self) -> QFrame:
        self.footer_panel = QFrame(self.app_shell)
        self.footer_panel.setObjectName("footerPanel")
        self.footer_panel.setMinimumHeight(108)

        layout = QVBoxLayout(self.footer_panel)
        layout.setContentsMargins(26, 12, 26, 12)
        layout.setSpacing(8)

        services_row = QHBoxLayout()
        services_row.setObjectName("servicesRow")
        services_row.setSpacing(10)

        self.get_service_icon = QLabel(self.footer_panel)
        self.get_service_icon.setObjectName("getServiceIcon")
        self.get_service_icon.setFixedSize(26, 26)
        self._set_label_pixmap(
            self.get_service_icon,
            ":/weather/cloudy.svg",
            QSize(22, 22),
        )
        services_row.addWidget(self.get_service_icon)

        self.get_service_label = QLabel("GET - Open-Meteo", self.footer_panel)
        self.get_service_label.setObjectName("getServiceLabel")
        services_row.addWidget(self.get_service_label)
        services_row.addStretch(1)

        self.post_service_icon = QLabel(self.footer_panel)
        self.post_service_icon.setObjectName("postServiceIcon")
        self.post_service_icon.setFixedSize(26, 26)
        self._set_label_pixmap(
            self.post_service_icon,
            ":/icons/cloud-lightning.svg",
            QSize(22, 22),
        )
        services_row.addWidget(self.post_service_icon)

        self.post_service_label = QLabel(
            "POST - JSONPlaceholder",
            self.footer_panel,
        )
        self.post_service_label.setObjectName("postServiceLabel")
        services_row.addWidget(self.post_service_label)
        layout.addLayout(services_row)

        layout.addWidget(self._horizontal_separator("footerSeparator"))

        status_row = QHBoxLayout()
        status_row.setObjectName("globalStatusRow")
        status_row.setSpacing(9)

        self.global_status_icon = QLabel("⌁", self.footer_panel)
        self.global_status_icon.setObjectName("globalStatusIcon")
        self.global_status_icon.setFixedWidth(26)
        self.global_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.addWidget(self.global_status_icon)

        self.global_status_label = QLabel(
            "Estado de las solicitudes: esperando operaciones",
            self.footer_panel,
        )
        self.global_status_label.setObjectName("globalStatusLabel")
        status_row.addWidget(self.global_status_label, 1)
        layout.addLayout(status_row)

        return self.footer_panel

    # ------------------------------------------------------------------
    # Componentes auxiliares
    # ------------------------------------------------------------------
    def _build_metric(self, *, parent: QWidget, object_name: str, icon_path: str, title: str, value: str) -> tuple[QWidget, QLabel]:
        metric = QWidget(parent)
        metric.setObjectName(object_name)
        metric.setMinimumHeight(98)

        layout = QVBoxLayout(metric)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_label = QLabel(metric)
        icon_label.setObjectName(f"{object_name}Icon")
        icon_label.setFixedSize(34, 34)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_label_pixmap(icon_label, icon_path, QSize(30, 30))
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel(title, metric)
        title_label.setObjectName(f"{object_name}Title")
        title_label.setMinimumHeight(20)
        layout.addWidget(title_label)

        value_label = QLabel(value, metric)
        value_label.setObjectName(f"{object_name}Value")
        value_label.setMinimumHeight(27)
        layout.addWidget(value_label)

        return metric, value_label

    @staticmethod
    def _horizontal_separator(object_name: str) -> QFrame:
        line = QFrame()
        line.setObjectName(object_name)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        return line

    @staticmethod
    def _vertical_separator(object_name: str) -> QFrame:
        line = QFrame()
        line.setObjectName(object_name)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        return line

    @staticmethod
    def _set_label_pixmap(label: QLabel, resource_path: str, size: QSize) -> None:
        pixmap = QPixmap(resource_path)
        if pixmap.isNull():
            return
        label.setPixmap(
            pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    # ------------------------------------------------------------------
    # Comportamiento de la cabecera frameless
    # ------------------------------------------------------------------
    def eventFilter(self, watched, event) -> bool:  
        if watched in getattr(self, "_title_drag_targets", ()):
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._toggle_maximize_restore()
                    return True

            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    window_handle = self.windowHandle()
                    if window_handle is not None:
                        window_handle.startSystemMove()
                    return True

        return super().eventFilter(watched, event)

    def _toggle_maximize_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _connect_actions(self) -> None:
        self.search_button.clicked.connect(self._start_weather_request)
        self.location_input.returnPressed.connect(self._start_weather_request)
        self.submit_button.clicked.connect(self._start_registro_request)

    def _set_initial_state(self) -> None:
        self.city_label.setText("Esperando consulta")
        self.current_conditions_label.setText("Realiza una búsqueda")
        self.temperature_label.setText("-- °C")
        self.condition_label.setText("--")
        self.humidity_value.setText("-- %")
        self.wind_value.setText("-- km/h")
        self.observation_time_value.setText("--")
        self.coordinates_label.setText("--")
        self.weather_icon.clear()
        self.post_city_label.setText("Ciudad: --")
        self.post_temperature_label.setText("Temperatura: -- °C")
        self.submit_button.setEnabled(False)
        self.request_status_label.setText("Consulta el clima antes de registrar")
        self.global_status_label.setText(
            "Estado de las solicitudes: esperando consulta"
        )


    def _start_weather_request(self) -> None:
        if self._weather_thread is not None:
            return

        city = self.location_input.text()
        thread = QThread(self)
        worker = WeatherWorker(city)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.result.connect(self._handle_weather_result)
        worker.error.connect(self._handle_weather_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._weather_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._weather_thread = thread
        self._weather_worker = worker
        self.location_input.setEnabled(False)
        self.search_button.setEnabled(False)
        self.global_status_label.setText("Consultando condiciones meteorológicas...")
        thread.start()

    def _handle_weather_result(self, weather: WeatherData) -> None:
        self.current_weather = weather
        location = f"{weather.city}, {weather.country}"
        self.city_label.setText(location)
        self.current_conditions_label.setText("Condiciones actuales")
        self.temperature_label.setText(f"{weather.temperature_c:.1f} °C")
        self.condition_label.setText(weather.condition)
        self.humidity_value.setText(f"{weather.humidity_percent} %")
        self.wind_value.setText(f"{weather.wind_speed_kmh:.1f} km/h")
        self.observation_time_value.setText(
            self._format_observation_time(weather.observed_at)
        )
        self.coordinates_label.setText(
            self._format_coordinates(weather.latitude, weather.longitude)
        )
        self._set_label_pixmap(
            self.weather_icon,
            self._weather_icon_path(weather.weather_code, weather.is_day),
            QSize(88, 88),
        )
        self.post_city_label.setText(f"Ciudad: {weather.city}")
        self.post_temperature_label.setText(
            f"Temperatura: {weather.temperature_c:.1f} °C"
        )
        self.submit_button.setEnabled(self._registro_thread is None)
        self.request_status_label.setText("Listo para registrar una observación")
        self.global_status_label.setText(f"Consulta completada: {location}")

    def _handle_weather_error(self, error: Exception) -> None:
        message = self._service_error_message(error)
        self.global_status_label.setText(f"Error de consulta: {message}")
        if self.current_weather is None:
            self.current_conditions_label.setText("No fue posible consultar el clima")

    def _weather_thread_finished(self) -> None:
        self._weather_thread = None
        self._weather_worker = None
        if not self._close_requested:
            self.location_input.setEnabled(True)
            self.search_button.setEnabled(True)
        self._finish_close_if_ready()

    def _start_registro_request(self) -> None:
        if self._registro_thread is not None:
            return
        if self.current_weather is None:
            self.request_status_label.setText(
                "Primero realiza una consulta meteorológica válida"
            )
            return

        weather = self.current_weather
        thread = QThread(self)
        worker = RegistroWorker(
            city=weather.city,
            temperature_c=weather.temperature_c,
            observation=self.observation_input.toPlainText(),
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.result.connect(self._handle_registro_result)
        worker.error.connect(self._handle_registro_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._registro_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._registro_thread = thread
        self._registro_worker = worker
        self.submit_button.setEnabled(False)
        self.request_status_label.setText("Enviando registro...")
        self.global_status_label.setText("Enviando observación a JSONPlaceholder...")
        thread.start()

    def _handle_registro_result(self, result: RegistroResult) -> None:
        self.observation_input.clear()
        self.request_status_label.setText("Registro enviado correctamente")
        self.global_status_label.setText(
            f"Registro de {result.city} enviado correctamente"
        )
        self._show_post_success_dialog(result)

    def _show_post_success_dialog(self, result: RegistroResult) -> None:
        overlay = QWidget(self.central_widget)
        overlay.setObjectName("postModalOverlay")
        overlay.setGeometry(self.central_widget.rect())
        overlay.show()
        overlay.raise_()

        blur = QGraphicsBlurEffect(self.central_widget)
        blur.setBlurRadius(5.0)
        self.central_widget.setGraphicsEffect(blur)

        dialog = PostSuccessDialog(result, self)
        dialog.finished.connect(self._restore_post_success_background)
        self._post_modal_overlay = overlay
        self._post_modal_blur = blur
        self._post_success_dialog = dialog
        dialog.open()

    def _restore_post_success_background(self) -> None:
        overlay = self._post_modal_overlay
        self._post_modal_overlay = None
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()

        blur = self._post_modal_blur
        self._post_modal_blur = None
        if blur is not None and self.central_widget.graphicsEffect() is blur:
            blur.setEnabled(False)
            blur.deleteLater()

        dialog = self._post_success_dialog
        self._post_success_dialog = None
        if dialog is not None:
            dialog.deleteLater()

    def _handle_registro_error(self, error: Exception) -> None:
        message = self._service_error_message(error)
        self.request_status_label.setText(f"No se pudo enviar: {message}")
        self.global_status_label.setText(f"Error de registro: {message}")

    def _registro_thread_finished(self) -> None:
        self._registro_thread = None
        self._registro_worker = None
        if not self._close_requested and self.current_weather is not None:
            self.submit_button.setEnabled(True)
        self._finish_close_if_ready()

    @staticmethod
    def _format_observation_time(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value

    @staticmethod
    def _format_coordinates(latitude: float, longitude: float) -> str:
        latitude_side = "N" if latitude >= 0 else "S"
        longitude_side = "E" if longitude >= 0 else "O"
        return (
            f"{abs(latitude):.4f}° {latitude_side} · "
            f"{abs(longitude):.4f}° {longitude_side}"
        )

    @staticmethod
    def _weather_icon_path(weather_code: int, is_day: bool) -> str:
        period = "day" if is_day else "night"
        if weather_code == 0:
            return f":/weather/clear-{period}.svg"
        if weather_code in (1, 2):
            return f":/weather/mostly-clear-{period}.svg"
        if weather_code in range(51, 58):
            return ":/weather/drizzle.svg"
        if weather_code in (*range(61, 68), *range(80, 83)):
            return ":/weather/rain.svg"
        if weather_code in (95, 96, 99):
            return ":/weather/thunderstorms.svg"
        if weather_code == 3:
            return ":/weather/overcast.svg"
        return ":/weather/cloudy.svg"

    @staticmethod
    def _service_error_message(error: Exception) -> str:
        if isinstance(error, InputValidationError):
            return str(error)
        if isinstance(error, CityNotFoundError):
            return str(error)
        if isinstance(error, TimeoutServiceError):
            return "El servicio tardó demasiado en responder"
        if isinstance(error, ConnectionServiceError):
            return "Sin conexión con el servicio"
        if isinstance(error, HttpStatusServiceError):
            if error.status_code is not None:
                return f"Respuesta HTTP {error.status_code}"
            return "Respuesta HTTP no válida"
        if isinstance(error, InvalidJsonServiceError):
            return "El servicio devolvió datos no válidos"
        if isinstance(error, InvalidResponseServiceError):
            return "La respuesta no contiene los datos esperados"
        if isinstance(error, RequestServiceError):
            return "No fue posible completar la solicitud"
        return "Ocurrió un error inesperado"

    def closeEvent(self, event: QCloseEvent) -> None:  
        threads = (self._weather_thread, self._registro_thread)
        if any(thread is not None and thread.isRunning() for thread in threads):
            self._close_requested = True
            self.location_input.setEnabled(False)
            self.search_button.setEnabled(False)
            self.submit_button.setEnabled(False)
            self.global_status_label.setText("Finalizando solicitud en curso...")
            event.ignore()
            return
        super().closeEvent(event)

    def _finish_close_if_ready(self) -> None:
        if (
            self._close_requested
            and self._weather_thread is None
            and self._registro_thread is None
        ):
            QTimer.singleShot(0, self.close)

    def _configure_tab_order(self) -> None:
        self.setTabOrder(self.location_input, self.search_button)
        self.setTabOrder(self.search_button, self.observation_input)
        self.setTabOrder(self.observation_input, self.submit_button)
