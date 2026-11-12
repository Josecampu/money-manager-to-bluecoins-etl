"""Carga del DataFrame ya transformado al CSV de importación de Bluecoins.

No inserta en una base de Bluecoins. El "load" de este ETL es un archivo
con las 14 columnas numeradas que pide la plantilla avanzada, en ese orden.
``run_load_pipeline`` solo encadena el renombre de columnas y la escritura.
"""

import csv

import pandas as pd


def map_to_bluecoins_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Arma un DataFrame nuevo con los encabezados exactos de Bluecoins.

    Se construye columna por columna, en lugar de renombrar el DataFrame de
    la transformación, para soltar campos internos que Bluecoins no importa
    (``ZMONEY``, ``ctgUid``, ``assetUid``) y para imponer el orden del
    archivo. Las columnas 13 y 14 existen en la plantilla y salen vacías:
    este ETL no trae estado ni desglose (split) desde Money Manager.

    El número entre paréntesis forma parte del nombre de columna. Quitarlo
    haría que el importador no reconozca el archivo.
    """
    df_load = pd.DataFrame()

    # 1. Mapeo de columnas existentes a los nombres de Bluecoins
    df_load['(1)Type'] = df['D_TRANSACTION_TYPE']
    df_load['(2)Date'] = df['D_TRANSACTION_DATE']
    df_load['(3)Item or Payee'] = df['D_DESCRIPTION']
    df_load['(4)Amount'] = df['D_AMOUNT']
    df_load['(5)Currency'] = df['D_CURRENCY']
    df_load['(6)ConversionRate'] = df['EXCHANGE_RATE']
    df_load['(7)Category Type'] = df['D_CATEGORY_TYPE']
    df_load['(8)Category'] = df['D_CATEGORY']
    df_load['(9)Account Type'] = df['D_ACCOUNT_TYPE']
    df_load['(10)Account'] = df['D_ACCOUNT_NAME']
    df_load['(11)Notes'] = df['NOTE']
    df_load['(12)Label'] = df['TAGS']

    # 2. Columnas adicionales requeridas por la estructura que van vacías por defecto
    df_load['(13)Status'] = ''
    df_load['(14)Split'] = ''

    return df_load


def export_to_csv(df: pd.DataFrame, output_filepath: str) -> None:
    """Escribe el CSV en UTF-8, sin índice de pandas y con comillas mínimas.

    ``QUOTE_MINIMAL`` entrecomilla solo las celdas que contienen coma, comilla
    o salto de línea. Las notas ya llegan en una sola línea desde
    ``clean_text_field``, así que la mayoría de las filas salen sin comillas.

    ``float_format='%.0f'`` escribe monto y tasa de cambio sin decimales.
    En esta base casi todos los montos COP ya son enteros, pero seis
    entradas de transferencia en dólares (recargas, montos como 485.01) y
    sus tasas pierden la parte decimal en el archivo. El redondeo es el
    formato de escritura, no un cambio del DataFrame en memoria.
    """
    df.to_csv(
        output_filepath,
        index=False,
        encoding='utf-8',
        float_format='%.0f',      # Asegura un formato numérico financiero estándar limpio
                      # Fuerza el punto como separador decimal
        quoting=csv.QUOTE_MINIMAL # Envuelve en comillas dobles solo las celdas que lo requieran (ej. notas con saltos de línea)
    )
    print(f"Archivo exportado exitosamente a: {output_filepath}")


def run_load_pipeline(df_transformed: pd.DataFrame, output_filepath: str = "bluecoins_import.csv") -> None:
    """Renombra al esquema de Bluecoins y escribe ``output_filepath``.

    El valor por defecto del argumento es ``bluecoins_import.csv``. ``main.py``
    no lo usa: pasa ``bluecoins_ready_import.csv``. La función no devuelve el
    DataFrame mapeado; el resultado queda solo en el archivo.
    """
    df_mapped = map_to_bluecoins_schema(df_transformed)
    export_to_csv(df_mapped, output_filepath)
