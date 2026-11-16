# Geocodificación y consulta meteorológica GET.

"""
Servicio meteorológico de Open-Meteo.

Responsabilidades:
- Buscar ciudades mediante geocodificación.
- Obtener sus coordenadas geográficas.
- Consultar las condiciones meteorológicas actuales.
- Validar y transformar las respuestas JSON en objetos del dominio.

Este módulo no depende de PySide6: su única responsabilidad es
la comunicación y procesamiento de datos del servicio REST.
"""

from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any
import requests
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

# Constantes Nombre del servicio y timeout base
SERVICE_NAME = "Open-Meteo"
DEFAULT_TIMEOUT = 10.0

# Endpoints oficiales usados por el servicio 
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Traducción de los códigos meteorológicos WMO utilizados por Open-Meteo.
# Se mantiene a nivel de módulo para no reconstruir el diccionario cada vez que se procesa una consulta.
WMO_WEATHER_CODES: dict[int, str] = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna ligera",
    53: "Llovizna moderada",
    55: "Llovizna intensa",
    56: "Llovizna helada ligera",
    57: "Llovizna helada intensa",
    61: "Lluvia ligera",
    63: "Lluvia moderada",
    65: "Lluvia intensa",
    66: "Lluvia helada ligera",
    67: "Lluvia helada intensa",
    71: "Nevada ligera",
    73: "Nevada moderada",
    75: "Nevada intensa",
    77: "Granos de nieve",
    80: "Chubascos ligeros",
    81: "Chubascos moderados",
    82: "Chubascos intensos",
    85: "Nevadas ligeras",
    86: "Nevadas intensas",
    95: "Tormenta",
    96: "Tormenta con granizo ligero",
    99: "Tormenta con granizo intenso",
}

@dataclass
class CityLocation:
    """ representa una ubicación devuelta por el servicio de geocodificacion"""
    name: str
    latitude: float
    longitude: float
    country: str
    region: str | None

@dataclass(frozen=True, slots=True)
class WeatherData:
    """ contiene los datos meteorológicos procesados que consumira la interfaz"""
    city: str
    region: str | None
    country: str
    latitude: float
    longitude: float
    temperature_c: float
    humidity_percent: int
    wind_speed_kmh: float
    weather_code: int
    condition: str
    is_day: bool
    observed_at: str
    timezone: str


class WeatherService:
    """ gwstiona las consultas GET necesarias para obtener el clima actual."""
    def __init__(self, timeout: float = DEFAULT_TIMEOUT, session: requests.Session | None = None) -> None:
        """
        Inicializa el servicio con un tiempo máximo de espera.

        Una Session permite reutilizar conexiones HTTP entre consultas.
        También puede inyectarse una sesión externa para facilitar pruebas.
        """

        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
            raise InputValidationError("El tiempo de espera debe ser un número finito mayor que cero.")

        self._timeout = float(timeout)

        # Si el servicio crea la sesión, también será responsable de cerrarla cuando deje de utilizarse.
        self._owns_session = session is None
        self._session = (session if session is not None else requests.Session())

    def get_weather(self, city_name: str) -> WeatherData:
        """
        Obtiene y procesa el clima actual de una ciudad.

        Flujo:
        1. Validar el nombre recibido.
        2. Resolver la ciudad mediante geocodificación.
        3. Consultar las condiciones meteorológicas actuales.
        4. Transformar la respuesta JSON en WeatherData.
        """

        if not isinstance(city_name, str):
            raise InputValidationError("El nombre de la ciudad debe ser una cadena de texto")
        city_name = city_name.strip()

        if len(city_name) < 2:
            raise InputValidationError("Debes introducir un nombre de ciudad de al menos 2 caracteres")

        # Open-Meteo necesita coordenadas para consultar el clima, por lo que primero se resuelve el nombre de la ciudad.
        location = self._search_city(city_name)

        # una vez obtenidas las coordenadas, se consultan las condiciones meteorológicas actuales.
        weather_json = self._fetch_current_weather(location)

        # La interfaz recibe un objeto estable y procesado, nunca el JSON original de la API.
        return self._build_weather_data(location, weather_json)


    def _get_json(self, url: str, params: dict[str, str | int | float], operation: str) -> dict[str, Any]:
        """
        Ejecuta una petición GET y devuelve un objeto JSON validado.

        Centralizar las llamadas HTTP permite aplicar de forma uniforme:
        - Timeouts.
        - Validación de códigos HTTP.
        - Deserialización JSON.
        - Traducción de excepciones de Requests.
        """
        service_context = f"{SERVICE_NAME} ({operation})"

        try:
            response = self._session.get(url, params=params, timeout=self._timeout)

            # convierte automaticamente  respuestas HTTP 4xx y 5xx en requests.exceptions.HTTPError.
            response.raise_for_status()

            # raise_for_status() no considera todos los estados fuera de 2xx como errores. Nuestra aplicación solo acepta 2xx.
            if not 200 <= response.status_code < 300:
                raise HttpStatusServiceError(service_context, response.status_code)
            
            try:
                # Deserializa el cuerpo de la respuesta HTTP.
                data = response.json()
            except ValueError as error:
                # Se recibió una respuesta, pero su cuerpo no pudo convertirse correctamente desde JSON.
                raise InvalidJsonServiceError(f"{service_context}: la respuesta no contiene JSON válido.") from error

            # Open-Meteo debe devolver un objeto JSON.
            # Una lista, string u otro tipo indica una respuesta inesperada.
            if not isinstance(data, dict):
                raise InvalidResponseServiceError(f"{service_context}: la estructura JSON recibida no es válida")

            return data

        except requests.exceptions.Timeout as error:
            raise TimeoutServiceError(
                f"{service_context}: "
                f"el servidor no respondió en {self._timeout:g} segundos."
            ) from error

        except requests.exceptions.ConnectionError as error:
            raise ConnectionServiceError(
                f"{service_context}: "
                "no fue posible establecer conexión. Comprueba tu conexión a Internet."
            ) from error

        except requests.exceptions.HTTPError as error:
            status_code = (error.response.status_code if error.response is not None else None)

            raise HttpStatusServiceError(service_context, status_code) from error

        except requests.exceptions.RequestException as error:
            # Captura cualquier otro fallo de Requests que no pertenezca a las categorías anteriores.
            raise RequestServiceError(
                f"{service_context}: "
                "se produjo un error durante la solicitud HTTP."
            ) from error
    
    def _search_city(self, city_name: str) -> CityLocation:
        """
        Busca una ciudad mediante la API de geocodificación.

        Devuelve únicamente la primera coincidencia encontrada, suficiente para el alcance actual de la aplicación.
        """

        params = {
            "name": city_name,
            "count": 1,
            "language": "es",
            "format": "json",
        }

        data = self._get_json(
            url=GEOCODING_URL,
            params=params,
            operation="geocodificación",
        )

        # Open-Meteo puede no incluir "results" cuando la búsqueda no produce coincidencias.
        results = data.get("results", [])
        if not isinstance(results, list):
            raise InvalidResponseServiceError("La API de geocodificación devolvió resultados inválidos")

        # no encontrar una ciudad es una situación controlable, no un error de conexión ni un error HTTP.
        if not results:
            raise CityNotFoundError(f"No se encontró la ciudad '{city_name}'")

        first_result = results[0]

        if not isinstance(first_result, dict):
            raise InvalidResponseServiceError(f"La información de la ciudad '{city_name}' tiene un formato incorrecto.")

        name = first_result.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvalidResponseServiceError("La API no devolvió un nombre de ciudad válido")

        latitude = self._require_number(first_result, "latitude", "geocodificación")

        longitude = self._require_number(first_result, "longitude", "geocodificación")

        # Además de ser números válidos, las coordenadas deben encontrarse dentro de sus rangos geográficos.
        if not -90 <= latitude <= 90:
            raise InvalidResponseServiceError("La API devolvió una latitud fuera del rango permitido.")

        if not -180 <= longitude <= 180:
            raise InvalidResponseServiceError("La API devolvió una longitud fuera del rango permitido")

        country_value = first_result.get("country")
        region_value = first_result.get("admin1")

        # pais y region pueden no estar disponibles para determinados resultados de geocodificación.
        country = (
            country_value.strip() if isinstance(country_value, str) and country_value.strip() else "País no identificado"
        )

        region = (
            region_value.strip() if isinstance(region_value, str) and region_value.strip() else None
        )

        return CityLocation(
            name=name.strip(),
            latitude=latitude,
            longitude=longitude,
            country=country,
            region=region,
        )

    def _fetch_current_weather(self, location: CityLocation) -> dict[str, Any]:
        """
        Consulta las condiciones meteorológicas actuales.

        Solo se solicitan las variables utilizadas por la aplicación para evitar recibir información innecesaria.
        """

        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "weather_code,"
                "is_day,"
                "wind_speed_10m"
            ),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }

        return self._get_json(
            url=WEATHER_URL,
            params=params,
            operation="consulta meteorológica",
        )


    def _build_weather_data(self, location: CityLocation, response_data: dict[str, Any]) -> WeatherData:
        """
        Valida la respuesta meteorológica y construye WeatherData.

        La interfaz recibe únicamente datos ya comprobados y preparados para ser representados en sus controles visuales.
        """

        current = response_data.get("current")
        if not isinstance(current, dict):
            raise InvalidResponseServiceError("La respuesta meteorológica no contiene datos actuales válidos")

        temperature = self._require_number(
            current,
            "temperature_2m",
            "consulta meteorológica",
        )

        humidity = self._require_number(
            current,
            "relative_humidity_2m",
            "consulta meteorológica",
        )

        wind_speed = self._require_number(
            current,
            "wind_speed_10m",
            "consulta meteorológica",
        )

        weather_code = current.get("weather_code")

        if (isinstance(weather_code, bool) or not isinstance(weather_code, int)):
            raise InvalidResponseServiceError("El código meteorológico recibido no es válido")

        is_day_value = current.get("is_day")

        # Open-Meteo representa día/noche mediante 1 y 0.
        if (isinstance(is_day_value, bool) or not isinstance(is_day_value, int) or is_day_value not in (0, 1)):
            raise InvalidResponseServiceError("El indicador de día o noche no es válido")

        # Validaciones semánticas adicionales.
        if not 0 <= humidity <= 100:
            raise InvalidResponseServiceError("El porcentaje de humedad recibido está fuera de rango.")

        if wind_speed < 0:
            raise InvalidResponseServiceError("La velocidad del viento recibida no es válida.")

        observed_at = current.get("time")
        timezone = response_data.get("timezone")

        if (not isinstance(observed_at, str) or not observed_at.strip()):
            raise InvalidResponseServiceError("La API no devolvió una hora de observación válida")

        if (not isinstance(timezone, str) or not timezone.strip()):
            raise InvalidResponseServiceError("La API no devolvió una zona horaria válida")

        return WeatherData(
            city=location.name,
            region=location.region,
            country=location.country,
            latitude=location.latitude,
            longitude=location.longitude,
            temperature_c=temperature,
            humidity_percent=round(humidity),
            wind_speed_kmh=wind_speed,
            weather_code=weather_code,
            condition=self._get_weather_description(weather_code),
            is_day=bool(is_day_value),
            observed_at=observed_at.strip(),
            timezone=timezone.strip(),
        )
    
    @staticmethod
    def _require_number(data: dict[str, Any], key: str, context: str) -> float:
        """
        Obtiene un campo numérico y comprueba que sea finito.

        Evita aceptar valores ausentes, booleanos, infinitos o NaN.
        """

        value = data.get(key)

        # bool es una subclase de int en Python.
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise InvalidResponseServiceError(
                f"{SERVICE_NAME} ({context}): "
                f"el campo '{key}'no contiene un número válido")
        return float(value)

    @staticmethod
    def _get_weather_description(weather_code: int) -> str:
        """
        traduce un código meteorológico WMO a una descripción comprensible.
        """

        # Si Open-Meteo incorpora un código que todavía no tenemos registrado, la aplicación continúa funcionando.
        return WMO_WEATHER_CODES.get(weather_code, (f"Condición no identificada: (código {weather_code})"))

    def close(self) -> None:
        """
        Libera la sesión HTTP creada internamente.

        Una sesión proporcionada desde fuera no se cierra aquí, ya que su ciclo de vida pertenece al código que la creó.
        """

        if self._owns_session:
            self._session.close()
