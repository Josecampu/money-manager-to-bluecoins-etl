"""Punto de entrada del ETL de Money Manager hacia Bluecoins.

Orquesta las tres etapas y no transforma filas por su cuenta:

1. ``extract.py`` lee ``money_android.sqlite`` en el rango de fechas.
2. ``transform.py`` limpia fechas, montos, textos, transferencias y tipos.
3. ``load.py`` escribe ``bluecoins_ready_import.csv``.

Rutas y fechas están fijas en el código. El rango 2017-01-01 a 2026-12-31
cubre el historial exportado y deja margen hasta el fin de 2026. Para otro
archivo o otro corte hay que editar estas constantes y volver a ejecutar
``python main.py`` desde esta carpeta, porque las rutas son relativas.
"""
import os
from extract import extract_raw_transactions
from load import run_load_pipeline
from transform import run_transformation_pipeline


def main():
    """Ejecuta extracción, transformación y carga en ese orden.

    Si la extracción falla (archivo ausente o SQL inválido), las etapas
    siguientes no corren: no hay captura de errores ni reintento. Los
    mensajes de conteo usan siempre ``len(df_raw)``, el tamaño recién
    salido de SQLite. No imprimen cuántas filas sobrevivieron a la
    transformación ni cuántas se escribieron en el CSV.
    """
# Configuraciones parametrizadas por entorno (con valores por defecto si no existen)
    db_path = os.getenv("ETL_DB_PATH", "money_android.sqlite")
    output_csv = os.getenv("ETL_OUTPUT_CSV", "bluecoins_ready_import.csv")
    START_DATE = os.getenv("ETL_START_DATE", "2017-01-01")
    END_DATE = os.getenv("ETL_END_DATE", "2026-12-31")
    TIMEZONE = os.getenv("ETL_TIMEZONE", "America/Bogota")

    print("1. Ejecutando Extracción...")
    df_raw = extract_raw_transactions(db_path, start_date=START_DATE, end_date=END_DATE)
    print(f"Registros extraídos en el rango: {len(df_raw)}")
    print(f"-> Filas extraídas de la BD: {len(df_raw)}")


    print("2. Ejecutando Transformación...")
    df_transformed = run_transformation_pipeline(df_raw, timezone=TIMEZONE)
    print(f"-> Filas extraídas de la BD: {len(df_raw)}")


    print("3. Ejecutando Carga...")
    run_load_pipeline(df_transformed, output_csv)
    print(f"-> Filas extraídas de la BD: {len(df_raw)}")

    print("¡Proceso ETL completado con éxito!")


if __name__ == "__main__":
    main()
