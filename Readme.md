# Money Manager to Bluecoins ETL Pipeline

Un pipeline ETL (Extract, Transform, Load) desarrollado en Python para automatizar la extracción, limpieza y migración de datos financieros desde la base de datos SQLite de **Money Manager** hacia un formato CSV estructurado y compatible con la importación directa en **Bluecoins**.

---

## 🛠️ Stack Tecnológico
- **Lenguaje:** Python 3.x
- **Librerías Principales:** `pandas`, `sqlite3`, `os`
- **Patrón de Arquitectura:** Modular (Separación estricta de responsabilidades en capas ETL)
- **Buenas Prácticas:** Configuración parametrizada mediante variables de entorno.

---

## 📂 Arquitectura del Proyecto

El proyecto está diseñado bajo un enfoque modular para facilitar la mantenibilidad, pruebas y escalabilidad:

```text
money-manager-to-bluecoins-etl/
├── main.py                  # Orquestador principal y gestión de entorno
├── extract.py               # Capa Extract: Conexión segura en solo lectura a SQLite
├── transform.py             # Capa Transform: Limpieza, fechas, divisas y tipos de transacción
├── load.py                  # Capa Load: Generación del archivo CSV final para Bluecoins
├── money_android.sqlite     # Base de datos de origen (Money Manager)
└── README.md                # Documentación del proyecto
```

---

## 🔄 Flujo de Trabajo (ETL)

1. **Extract (`extract.py`):**
   - Conexión lógica en solo lectura a la base de datos SQLite.
   - Extracción de transacciones utilizando consultas parametrizadas para evitar inyecciones SQL.
   - Resolución de cuentas, categorías, etiquetas y mapeos estructurales (como tarjetas de débito y patrones de divisas).

2. **Transform (`transform.py`):**
   - Conversión de marcas de tiempo (`ZDATE`) desde milisegundos Unix a fechas legibles con soporte de huso horario parametrizado (`America/Bogota` por defecto).
   - Normalización de códigos de divisas (ej. `COP_COP` a `COP`).
   - Limpieza de montos (`AMOUNT`), manejo de signos según el tipo de transacción (`DO_TYPE`) y resolución de transferencias.
   - Limpieza y saneamiento de campos de texto (`NOTE`, `D_DESCRIPTION`).

3. **Load (`load.py` & `main.py`):**
   - Validación final del DataFrame transformado.
   - Exportación estructurada al archivo `bluecoins_ready_import.csv` listo para su importación.

---

## ⚙️ Configuración (Variables de Entorno)

El pipeline soporta la parametrización de sus rutas, rangos de fechas y zona horaria a través de variables de entorno, permitiendo su ejecución flexible sin modificar el código fuente:

| Variable | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| `ETL_DB_PATH` | Ruta de la base de datos SQLite de origen | `money_android.sqlite` |
| `ETL_OUTPUT_CSV` | Ruta del archivo CSV de salida | `bluecoins_ready_import.csv` |
| `ETL_START_DATE` | Fecha de inicio para la extracción (`YYYY-MM-DD`) | `2017-01-01` |
| `ETL_END_DATE` | Fecha de fin para la extracción (`YYYY-MM-DD`) | `2026-12-31` |
| `ETL_TIMEZONE` | Zona horaria objetivo para las fechas | `America/Bogota` |

---

## 🚀 Guía de Instalación y Ejecución

### 1. Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/money-manager-to-bluecoins-etl.git
cd money-manager-to-bluecoins-etl
```

### 2. Instalar dependencias
Asegúrate de tener Python instalado y ejecuta:
```bash
pip install pandas
```

### 3. Colocar la base de datos
Asegúrate de ubicar tu archivo de respaldo de Money Manager (`money_android.sqlite`) en la raíz del proyecto.

### 4. Ejecutar el pipeline
Puedes ejecutar el script directamente:
```bash
python main.py
```

O bien, definir variables de entorno en tu terminal antes de correrlo (opcional):
```powershell
$env:ETL_START_DATE="2024-01-01"
python main.py
```