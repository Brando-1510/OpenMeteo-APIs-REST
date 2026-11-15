# Enviar registros mediante POST.
"""
Servicio de registro mediante HTTP POST.

Responsabilidades:
- Recibir información procedente del formulario.
- Validar los datos antes de enviarlos.
- Construir el payload JSON.
- Ejecutar una solicitud HTTP POST.
- Validar el código de estado HTTP.
- Deserializar y validar la respuesta JSON.

utiliza JSONPlaceholder como API REST de pruebas.

"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import requests

from app.services.exceptions import (
    ConnectionServiceError,
    HttpStatusServiceError,
    InvalidJsonServiceError,
    InvalidResponseServiceError,
    InputValidationError,
    RequestServiceError,
    TimeoutServiceError,
)


SERVICE_NAME = "JSONPlaceholder"
DEFAULT_TIMEOUT = 10.0

# Endpoint para demostrar solicitudes HTTP POST.
REGISTRO_URL = "https://jsonplaceholder.typicode.com/posts"


@dataclass(frozen=True, slots=True)
class RegistroResult:
    """ rpresenta el resultado procesado de una operación POST exitosa."""

    record_id: int | str
    status_code: int
    city: str
    temperature_c: float
    observation: str
    response_data: dict[str, Any]


class RegistroService:
    """Gestiona el envío de registros mediante solicitudes HTTP POST."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, session: requests.Session | None = None) -> None:
        """
        Inicializa el servicio de registros.
        se puede proporcionar una Session externa para facilitar pruebas o reutilizar conexiones HTTP desde otro componente.
        """

        # bool se excluye explícitamente de la validación numérica.
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
            raise InputValidationError("El tiempo de espera debe ser un número finito mayor que cero.")

        self._timeout = float(timeout)

        # si el servicio crea la sesión, también la cierra despues de usarse
        self._owns_session = session is None
        self._session = (session if session is not None else requests.Session())

    def create_record(self, city: str, temperature_c: float, observation: str) -> RegistroResult:
        """
        Construye y envia un registro meteorologico mediante HTTP POST.

        Los datos recibidos normalmente procederán de los controlesde la interfaz gráfica.
        """

        # Validamos los tipos antes de utilizar métodos como strip().
        if not isinstance(city, str):
            raise InputValidationError("La ciudad debe ser una cadena de texto")
        if not isinstance(observation, str):
            raise InputValidationError("La observación debe ser una cadena de texto")

        city = city.strip()
        observation = observation.strip()

        # Evitamos realizar solicitudes con campos obligatorios vacíos.
        if not city:
            raise InputValidationError("La ciudad es obligatoria")
        if not observation:
            raise InputValidationError("La observación debe se obligatoria")

        # La temperatura debe ser numérica, finita y no booleana.
        if ( isinstance(temperature_c, bool) or not isinstance(temperature_c, (int, float)) or not math.isfinite(temperature_c)):
            raise InputValidationError("La temperatura debe ser un número válido")

        temperature = float(temperature_c)

        # JSONPlaceholder utiliza publicaciones con los campos
        # title, body y userId. Adaptamos nuestros datos meteorológicos a esa estructura 
        payload = {
            "title": f"Registro meteorológico: {city}",
            "body": (
                f"Temperatura: {temperature:.1f} °C\n"
                f"Observacion: {observation}"
            ),
            "userId": 1,
        }

        # ejecutamos la solicitud y recibimos únicamente datos HTTP y JSON que ya fueron validados.
        status_code, response_data = self._post_json(payload)

        # yna creación exitosa debe devolver un identificador que permita reconocer el recurso simulado.
        record_id = response_data.get("id")
        if (isinstance(record_id, bool) or not isinstance(record_id, (int, str)) or not str(record_id).strip()):
            raise InvalidResponseServiceError(
                f"{SERVICE_NAME}: "
                "no se recibió un identificador válido")

        # La interfaz recibe un objeto organizado y no necesita interpretar directamente la respuesta de la API.
        return RegistroResult(
            record_id=record_id,
            status_code=status_code,
            city=city,
            temperature_c=temperature,
            observation=observation,
            response_data=response_data,
        )

    def _post_json(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """
        Ejecuta una solicitud POST y devuelve su respuesta JSON validada.

        Centraliza:
        - Serialización del payload.
        - Timeout.
        - Validación de códigos HTTP.
        - Deserialización JSON.
        - Traducción de excepciones de Requests.
        """

        try:
            # json= serializa automáticamente el diccionario a JSON y configura Content-Type como application/json.
            response = self._session.post(
                REGISTRO_URL,
                json=payload,
                timeout=self._timeout,
            )

            # Convierte respuestas HTTP 4xx y 5xx en HTTPError.
            response.raise_for_status()

            # solo aceptamos respuestas exitosas 2xx.
            if not 200 <= response.status_code < 300:
                raise HttpStatusServiceError(
                    SERVICE_NAME,
                    response.status_code,
                )

            try:
                # Convertimos el cuerpo JSON recibido nuevamente a estructuras nativas de Python.
                response_data = response.json()

            except ValueError as error:
                raise InvalidJsonServiceError(
                    f"{SERVICE_NAME}: "
                    "el servidor no devolvió JSON válido") from error

            # El servicio debe devolver un objeto JSON.
            if not isinstance(response_data, dict):
                raise InvalidResponseServiceError(
                    f"{SERVICE_NAME}: "
                    "la respuesta no tiene la estructura esperada")

            return response.status_code, response_data

        except requests.exceptions.Timeout as error:
            raise TimeoutServiceError(
                f"{SERVICE_NAME}: "
                f"el servidor no respondió en {self._timeout:g} segundos."
            ) from error

        except requests.exceptions.ConnectionError as error:
            raise ConnectionServiceError(
                f"{SERVICE_NAME}: "
                "no fue posible establecer conexión. "
                "Comprueba tu conexión a Internet."
            ) from error

        except requests.exceptions.HTTPError as error:
            # Conservamos el código HTTP original para identificar correctamente errores 4xx, 5xx u otros estados.
            status_code = (error.response.status_code if error.response is not None else None)

            raise HttpStatusServiceError(
                SERVICE_NAME,
                status_code,
            ) from error

        except requests.exceptions.RequestException as error:
            # Captura cualquier otro error propio de Requests que no haya sido clasificado anteriormente.
            raise RequestServiceError(
                f"{SERVICE_NAME}: "
                "se produjo un error durante la solicitud POST."
            ) from error

    def close(self) -> None:
        """
        Libera la sesión HTTP creada internamente.

        Si la sesión fue proporcionada desde fuera del servicio, su ciclo de vida pertenece al componente que la creó.
        """
        if self._owns_session:
            self._session.close()