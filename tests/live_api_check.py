
"""
Prueba de integración de las APIs REST reales.

A diferencia de test_services.py, este archivo sí necesita conexión a Internet y realiza solicitudes HTTP reales.
"""

from app.services.weather_services import WeatherService
from app.services.registro_services import RegistroService
from app.services.exceptions import ServiceError

def main():
    weather_service = WeatherService(timeout=10)
    registro_service = RegistroService(timeout=10)

    try:
        print("\n=== PRUEBA GET: OPEN-METEO ===")

        weather = weather_service.get_weather("León")

        print(f"Ciudad: {weather.city}")
        print(f"País: {weather.country}")
        print(f"Temperatura: {weather.temperature_c} °C")
        print(f"Humedad: {weather.humidity_percent}%")
        print(f"Condición: {weather.condition}")
        print(f"Hora: {weather.observed_at}")

        print("\n=== PRUEBA POST: JSONPLACEHOLDER ===")

        result = registro_service.create_record(
            city=weather.city,
            temperature_c=weather.temperature_c,
            observation="Prueba de integración del cliente REST.",
        )

        print(f"ID recibido: {result.record_id}")
        print(f"Código HTTP: {result.status_code}")
        print(f"Ciudad registrada: {result.city}")

        print("\nPRUEBAS DE INTEGRACIÓN FINALIZADAS.")

    except ServiceError as error:
        print(f"\nERROR CONTROLADO: {error}")

    finally:
        # Liberamos ambas sesiones HTTP aunque ocurra un error.
        weather_service.close()
        registro_service.close()

if __name__ == "__main__":
    main()