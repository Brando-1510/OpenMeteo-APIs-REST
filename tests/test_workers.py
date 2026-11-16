
import unittest
from unittest.mock import patch

from app.services.exceptions import TimeoutServiceError
from app.services.registro_services import RegistroResult
from app.services.weather_services import WeatherData
from app.workers import RegistroWorker, WeatherWorker


class ServiceWorkerTests(unittest.TestCase):
    @patch("app.workers.service_workers.WeatherService")
    def test_weather_worker_emits_result_and_finishes(self, service_class):
        weather = WeatherData(
            city="León",
            region="León",
            country="Nicaragua",
            latitude=12.4379,
            longitude=-86.8780,
            temperature_c=29.5,
            humidity_percent=70,
            wind_speed_kmh=12.5,
            weather_code=2,
            condition="Parcialmente nublado",
            is_day=True,
            observed_at="2026-11-15T14:00",
            timezone="America/Managua",
        )
        service_class.return_value.get_weather.return_value = weather
        worker = WeatherWorker("León")
        results: list[WeatherData] = []
        finished: list[bool] = []
        worker.result.connect(results.append)
        worker.finished.connect(lambda: finished.append(True))

        worker.run()

        self.assertEqual(results, [weather])
        self.assertEqual(finished, [True])
        service_class.return_value.get_weather.assert_called_once_with("León")
        service_class.return_value.close.assert_called_once_with()

    @patch("app.workers.service_workers.WeatherService")
    def test_weather_worker_preserves_service_error(self, service_class):
        error = TimeoutServiceError("Tiempo agotado")
        service_class.return_value.get_weather.side_effect = error
        worker = WeatherWorker("León")
        errors: list[Exception] = []
        worker.error.connect(errors.append)

        worker.run()

        self.assertEqual(errors, [error])
        service_class.return_value.close.assert_called_once_with()

    @patch("app.workers.service_workers.RegistroService")
    def test_registro_worker_emits_result_and_finishes(self, service_class):
        result = RegistroResult(
            record_id=101,
            status_code=201,
            city="León",
            temperature_c=29.5,
            observation="Mucho calor",
            response_data={"id": 101},
        )
        service_class.return_value.create_record.return_value = result
        worker = RegistroWorker("León", 29.5, "Mucho calor")
        results: list[RegistroResult] = []
        finished: list[bool] = []
        worker.result.connect(results.append)
        worker.finished.connect(lambda: finished.append(True))

        worker.run()

        self.assertEqual(results, [result])
        self.assertEqual(finished, [True])
        service_class.return_value.create_record.assert_called_once_with(
            city="León",
            temperature_c=29.5,
            observation="Mucho calor",
        )
        service_class.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
