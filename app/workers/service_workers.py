
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
from app.services.exceptions import ServiceError
from app.services.registro_services import RegistroService
from app.services.weather_services import WeatherService


class WeatherWorker(QObject):
    result = Signal(object)
    error = Signal(object)
    finished = Signal()

    def __init__(self, city: str) -> None:
        super().__init__()
        self._city = city



    @Slot()
    def run(self) -> None:
        service: WeatherService | None = None
        try:
            service = WeatherService()
            self.result.emit(service.get_weather(self._city))
        except ServiceError as error:
            self.error.emit(error)
        except Exception as error:  # Protección del límite entre hilos.
            self.error.emit(error)
        finally:
            if service is not None:
                service.close()
            self.finished.emit()


class RegistroWorker(QObject):
    result = Signal(object)
    error = Signal(object)
    finished = Signal()

    def __init__(self, city: str,temperature_c: float, observation: str) -> None:
        super().__init__()
        self._city = city
        self._temperature_c = temperature_c
        self._observation = observation

    @Slot()
    def run(self) -> None:
        service: RegistroService | None = None
        try:
            service = RegistroService()
            result = service.create_record(
                city=self._city,
                temperature_c=self._temperature_c,
                observation=self._observation,
            )
            self.result.emit(result)
        except ServiceError as error:
            self.error.emit(error)
        except Exception as error:  # Protección del límite entre hilos.
            self.error.emit(error)
        finally:
            if service is not None:
                service.close()
            self.finished.emit()
