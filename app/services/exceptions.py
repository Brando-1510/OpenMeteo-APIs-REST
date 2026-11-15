# Centralizar las excepciones de la capa de servicios.

"""
Excepciones personalizadas para los services.

Centraliza los errores controlados producidos durante la comunicación
con servicios REST para que la interfaz gráfica pueda identificarlos
y mostrar mensajes comprensibles al usuario.
"""

class ServiceError(Exception):
    """Excepción base para errores de servicios."""
    pass

class InputValidationError(ServiceError):
    """Excepción para cuando los datos proporcioandos no son válidos."""
    pass

class CityNotFoundError(ServiceError):
    """Excepción para cuando no se encuentra la ciudad base proporcionada"""
    pass

class ConnectionServiceError(ServiceError):
    """Excepción para cuando no se puede establecer conexión con el servicio."""
    pass

class TimeoutServiceError(ServiceError):
    """Se produce cuando una solicitud supera el tiempo permitido"""
    pass

class HttpStatusServiceError(ServiceError):
    """Se produce cuando una API devuelve un código de estado HTTP incorrecto"""
    def __init__(self, service_name: str, status_code: int | None):
        self.service_name = service_name
        self.status_code = status_code

        if status_code is None:
            message = (f"{service_name}: no se pudo determinar el código de respuesta HTTP")
        elif status_code == 429:
            message = (f"{service_name}: se alcanzó el limite temporal de solicitudes al servicio HTTP 429")
        elif 400 <= status_code < 500:
            message = (f"{service_name}: la solicitud fue rehazada por el servidor (HTTP {status_code})")
        elif 500 <= status_code < 600:
            message = (f"{service_name}: el servidor presentó un problema inyerno  (HTTP {status_code})")
        else:
            message = (f"{service_name}: respuesta http inesperada {status_code}")
        super().__init__(message)

    class InvalidJsonServiceError(ServiceError):
        """Se produce cuando una API devuelve un contenido JSON inválido"""
        pass

    class InvalidResponseServiceError(ServiceError):
        """Se produce cuando la respuesta es válida, pero no contiene la estructura o los datos esperados."""
        pass

    class RequestServiceError(ServiceError):
        """Excepcion ante otro fallo controlado durante una solicitud HTTP"""
        pass







