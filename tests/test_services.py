
"""
Pruebas unitarias de los servicios REST.

Utilizamos unittest y unittest.mock para comprobar el
comportamiento de los servicios sin depender de Internet.

Las respuestas HTTP se simulan para poder reproducir
situaciones exitosas y errores de manera controlada.
"""

import unittest
from unittest.mock import Mock

import requests

from app.services.weather_services import WeatherService
from app.services.registro_services import RegistroService

from app.services.exceptions import (
    CityNotFoundError,
    ConnectionServiceError,
    HttpStatusServiceError,
    InvalidResponseServiceError,
    InvalidJsonServiceError,
    InputValidationError,
    TimeoutServiceError,
)


def create_response(status_code: int, data=None) -> requests.Response:
    """
    Construye una respuesta HTTP simulada.

    Utilizamos requests.Response para que sus métodos, incluido raise_for_status(), se comporten como los reales.
    """

    response = requests.Response()
    response.status_code = status_code
    response.url = "https://api.test.local"

    if data is not None:
        import json

        response._content = json.dumps(data).encode("utf-8")
        response.headers["Content-Type"] = "application/json"

    return response


class WeatherServiceTests(unittest.TestCase):
    """Pruebas unitarias del servicio meteorológico."""

    def setUp(self):
        # Creamos una sesión simulada para interceptar las peticiones GET.
        self.session = Mock(spec=requests.Session)

        self.service = WeatherService(
            timeout=5,
            session=self.session,
        )

    def tearDown(self):
        self.service.close()

    def configure_successful_weather(self):
        """Configura respuestas exitosas para geocodificación y clima."""

        geocoding_response = create_response(
            200,
            {
                "results": [
                    {
                        "name": "León",
                        "latitude": 12.4379,
                        "longitude": -86.8780,
                        "country": "Nicaragua",
                        "admin1": "León",
                    }
                ]
            },
        )

        weather_response = create_response(
            200,
            {
                "timezone": "America/Managua",
                "current": {
                    "temperature_2m": 29.5,
                    "relative_humidity_2m": 70,
                    "wind_speed_10m": 12.5,
                    "weather_code": 2,
                    "is_day": 1,
                    "time": "2026-11-15T14:00",
                },
            },
        )

        self.session.get.side_effect = [
            geocoding_response,
            weather_response,
        ]

    def test_get_weather_success(self):
        """Comprueba que se obtiene correctamente el clima."""

        self.configure_successful_weather()

        result = self.service.get_weather("León")

        self.assertEqual(result.city, "León")
        self.assertEqual(result.country, "Nicaragua")
        self.assertEqual(result.temperature_c, 29.5)
        self.assertEqual(result.humidity_percent, 70)
        self.assertEqual(result.condition, "Parcialmente nublado")

        # Se esperan dos solicitudes GET:
        # una de geocodificación y otra meteorológica.
        self.assertEqual(self.session.get.call_count, 2)

    def test_empty_city(self):
        """Comprueba que no se permita una ciudad vacía."""

        with self.assertRaises(InputValidationError):
            self.service.get_weather("   ")

        self.session.get.assert_not_called()

    def test_city_not_found(self):
        """Comprueba el comportamiento cuando no existe la ciudad."""

        self.session.get.return_value = create_response(
            200,
            {"results": []},
        )

        with self.assertRaises(CityNotFoundError):
            self.service.get_weather("CiudadInexistente")

    def test_connection_error(self):
        """Comprueba el manejo de una pérdida de conexión."""

        self.session.get.side_effect = requests.exceptions.ConnectionError()

        with self.assertRaises(ConnectionServiceError):
            self.service.get_weather("León")

    def test_timeout(self):
        """Comprueba el manejo de una solicitud que tarda demasiado."""

        self.session.get.side_effect = requests.exceptions.Timeout()

        with self.assertRaises(TimeoutServiceError):
            self.service.get_weather("León")

    def test_http_error(self):
        """Comprueba el manejo de una respuesta HTTP 503."""

        self.session.get.return_value = create_response(
            503,
            {"error": "Service unavailable"},
        )

        with self.assertRaises(HttpStatusServiceError) as context:
            self.service.get_weather("León")

        self.assertEqual(context.exception.status_code, 503)

    def test_invalid_json(self):
        """Comprueba el manejo de una respuesta que no contiene JSON válido."""

        response = create_response(200)
        response._content = b"esto no es json"

        self.session.get.return_value = response

        with self.assertRaises(InvalidJsonServiceError):
            self.service.get_weather("León")

    def test_http_client_error(self):
        """Comprueba una respuesta HTTP 404."""

        self.session.get.return_value = create_response(404, {})

        with self.assertRaises(HttpStatusServiceError) as context:
            self.service.get_weather("León")

        self.assertEqual(context.exception.status_code, 404)


class RegistroServiceTests(unittest.TestCase):
    """Pruebas unitarias del servicio de registros POST."""

    def setUp(self):
        # Simulamos la sesión para comprobar el envío POST.
        self.session = Mock(spec=requests.Session)

        self.service = RegistroService(
            timeout=5,
            session=self.session,
        )

    def tearDown(self):
        self.service.close()

    def test_create_record_success(self):
        """Comprueba el envío exitoso de un registro."""

        self.session.post.return_value = create_response(
            201,
            {
                "id": 101,
                "title": "Registro meteorológico: León",
                "body": "Temperatura: 29.5 °C",
                "userId": 1,
            },
        )

        result = self.service.create_record(
            city="León",
            temperature_c=29.5,
            observation="Mucho calor",
        )

        self.assertEqual(result.record_id, 101)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.city, "León")

        # Verificamos que los datos se enviaron mediante JSON.
        self.session.post.assert_called_once()

        sent_payload = self.session.post.call_args.kwargs["json"]

        self.assertEqual(sent_payload["userId"], 1)
        self.assertIn("León", sent_payload["title"])
        self.assertIn("Mucho calor", sent_payload["body"])

        # Verificamos que se estableció un timeout.
        self.assertEqual(
            self.session.post.call_args.kwargs["timeout"],
            5,
        )

    def test_empty_city(self):
        """Comprueba la validación de una ciudad vacía."""

        with self.assertRaises(InputValidationError):
            self.service.create_record(
                city=" ",
                temperature_c=29.5,
                observation="Mucho calor",
            )

        self.session.post.assert_not_called()

    def test_invalid_temperature(self):
        """Comprueba que se rechacen temperaturas no numéricas."""

        with self.assertRaises(InputValidationError):
            self.service.create_record(
                city="León",
                temperature_c=float("nan"),
                observation="Mucho calor",
            )

        self.session.post.assert_not_called()

    def test_connection_error(self):
        """Comprueba el manejo de errores de conexión POST."""

        self.session.post.side_effect = (
            requests.exceptions.ConnectionError()
        )

        with self.assertRaises(ConnectionServiceError):
            self.service.create_record(
                "León",
                29.5,
                "Mucho calor",
            )

    def test_timeout(self):
        """Comprueba el manejo de timeout POST."""

        self.session.post.side_effect = requests.exceptions.Timeout()

        with self.assertRaises(TimeoutServiceError):
            self.service.create_record(
                "León",
                29.5,
                "Mucho calor",
            )

    def test_http_error(self):
        """Comprueba el manejo de respuestas HTTP incorrectas."""

        self.session.post.return_value = create_response(
            500,
            {"error": "Internal server error"},
        )

        with self.assertRaises(HttpStatusServiceError) as context:
            self.service.create_record(
                "León",
                29.5,
                "Mucho calor",
            )

        self.assertEqual(context.exception.status_code, 500)

    def test_invalid_json_response(self):
        """Comprueba el manejo de JSON inválido en una respuesta POST."""

        response = create_response(201)
        response._content = b"respuesta incorrecta"

        self.session.post.return_value = response

        with self.assertRaises(InvalidJsonServiceError):
            self.service.create_record(
                "León",
                29.5,
                "Mucho calor",
            )

    def test_http_client_error(self):
        """Comprueba una respuesta HTTP 400."""

        self.session.post.return_value = create_response(400, {})

        with self.assertRaises(HttpStatusServiceError) as context:
            self.service.create_record(
                "León",
                29.5,
                "Prueba de error HTTP.",
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
