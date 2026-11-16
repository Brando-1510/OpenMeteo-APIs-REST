## Crear entorno virtual
Creamos el entorno virtual
```bash
python -m venv venv
```


## Activar entorno 

Activamos el entonro virtual antes de instalar dependencias:

```bash
.venv\Scripts\activate
```


## Instalar dependencias

Ejecuta para actualizar el gestor de paquetes e instalar las librerías del proyecto:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```


## Testing y pruebas de servicios REST

El proyecto utiliza el módulo `unittest` de Python para verificar
el funcionamiento de sus servicios HTTP.

### 1. Requisitos previos

- Entorno virtual activado.
- Dependencias instaladas.
- Ejecutar los comandos desde la raíz del proyecto.

### 2. Ejecutar pruebas unitarias

Para ejecutar todas las pruebas automatizadas:

```bash
python -m unittest discover -s tests -v
```

Estas pruebas utilizan respuestas HTTP simuladas mediante
`unittest.mock`, por lo que no requieren conexión a Internet.

Se comprueban:

- Consultas GET y solicitudes POST.
- Procesamiento y validación de JSON.
- Respuestas HTTP 2xx, 4xx y 5xx.
- Errores de conexión.
- Tiempo de espera (Timeout).
- Ciudades inexistentes.
- Respuestas JSON inválidas.
- Validación de datos de entrada.

### 3. Ejecutar pruebas de integración

Para comprobar la comunicación con las APIs reales:

```bash
python -m tests.live_api_check
```

Este comando realiza:

1. Una búsqueda geográfica y consulta meteorológica mediante Open-Meteo.
2. Un envío de información mediante POST a JSONPlaceholder.
3. La comprobación de las respuestas recibidas.

Esta prueba requiere conexión a Internet.

### 4. APIs utilizadas

| Servicio | Endpoint | Método |
|---|---|---|
| Open-Meteo Geocoding | geocoding-api.open-meteo.com/v1/search | GET |
| Open-Meteo Weather | api.open-meteo.com/v1/forecast | GET |
| JSONPlaceholder | jsonplaceholder.typicode.com/posts | POST |

### 5. Consideraciones

JSONPlaceholder es una API de pruebas.
Las solicitudes POST simulan la creación de recursos,
pero los registros no se almacenan permanentemente.

Las pruebas unitarias no necesitan Internet.
Las pruebas de integración sí dependen de los servicios externos.

### 6. Resultado esperado

Las pruebas unitarias deben finalizar con el resultado:

```text
Ran 16 tests

OK
```

Las pruebas de integración deben mostrar los datos
meteorológicos obtenidos y la respuesta del POST.

