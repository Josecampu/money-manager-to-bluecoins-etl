"""Transformación de movimientos de Money Manager al modelo de Bluecoins.

Cada función recibe un DataFrame, trabaja sobre una copia y devuelve otro
DataFrame. ``run_transformation_pipeline`` las encadena con ``pipe`` en un
orden fijo: varias funciones leen ``D_TRANSACTION_TYPE`` todavía como código
de Money Manager (``'0'``, ``'1'``, ``'3'``, ``'4'``). ``map_transaction_types``
tiene que ir después de ``clean_transfers`` y de ``clean_and_transform_amount``,
porque esas dos comparan contra esos códigos y no contra ``i``, ``e`` o ``t``.

En esta base hay 12.491 filas en ``INOUTCOME``:

* ``'0'`` ingreso (449)
* ``'1'`` gasto (8.303)
* ``'3'`` salida de transferencia (1.869), todas con monto positivo
* ``'4'`` entrada de transferencia (1.869)
* ``'7'`` un ingreso suelto, sin regla en el mapeo

Copiar el DataFrame en cada paso duplica memoria ocho veces. A este tamaño
no cambia el tiempo de corrida; el orden de las funciones sí cambia el resultado.
"""

import numpy as np
import pandas as pd


def clean_transaction_date(df: pd.DataFrame, timezone: str = "America/Bogota") -> pd.DataFrame:
    """Pasa ``ZDATE`` de milisegundos Unix a texto ``YYYY-MM-DD HH:MM:SS``.

    Money Manager guarda el instante en UTC. Aquí se interpreta con
    ``unit='ms'`` y ``utc=True``, se convierte al huso horario indicado
    y se quita la zona del texto, que es el formato que espera el CSV de
    Bluecoins. Si la columna no viene en el DataFrame, el resto del
    pipeline sigue igual.

    Los valores que no sean numéricos quedan vacíos (``NaT`` formateado
    como nulo) por ``errors='coerce'``.
    """
    df = df.copy()

    if 'D_TRANSACTION_DATE' in df.columns:
        # 1. Convertimos a numérico por seguridad
        numeric_dates = pd.to_numeric(df['D_TRANSACTION_DATE'], errors='coerce')

        # 2. Creamos el datetime en UTC estricto desde los milisegundos
        dt_utc = pd.to_datetime(numeric_dates, unit='ms', utc=True)

        # 3. Convertimos al huso horario parametrizado (ej. America/Bogota)
        dt_local = dt_utc.dt.tz_convert(timezone)

        # 4. Formateamos al string plano requerido por Bluecoins (sin zona horaria adjunta)
        df['D_TRANSACTION_DATE'] = dt_local.dt.strftime('%Y-%m-%d %H:%M:%S')

    return df


def clean_currency(df: pd.DataFrame) -> pd.DataFrame:
    """Se queda con el código de moneda de ``currencyUid``.

    En esta base el valor es ``COP_COP`` (60 cuentas) o ``COP_USD``
    (1 cuenta). ``split('_')`` y el último tramo devuelven ``COP`` o
    ``USD``. Una moneda sin guion bajo se conservaría entera. ``NaN`` se
    vuelve el texto ``'nan'`` porque la columna se fuerza a ``str`` antes
    de partirla.
    """
    df = df.copy()
    df['D_CURRENCY'] = df['D_CURRENCY'].astype(str).str.split('_').str[-1]
    return df


def clean_and_transform_amount(df: pd.DataFrame) -> pd.DataFrame:
    """Deja el monto en float y cambia el signo de las salidas de transferencia.

    ``DO_TYPE`` ``'3'`` es la pierna de salida. En la base esos montos vienen
    positivos; se multiplican por -1 para distinguirlos de la pierna ``'4'``,
    que permanece positiva. Los gastos (``'1'``) no se tocan: el comentario
    ``['1', '3']`` recuerda que negar el gasto se evaluó y se dejó fuera.

    La comparación pasa por ``str`` a propósito. En SQLite ``DO_TYPE`` es
    texto; si en otra exportación llegara como entero, ``'3'`` seguiría
    coincidiendo. No modifica la columna de tipo, solo ``D_AMOUNT``.
    """
    df = df.copy()

    # Aseguramos que D_AMOUNT sea float nativo de numpy/pandas estándar
    df['D_AMOUNT'] = df['D_AMOUNT'].astype(float)

    # Creamos la máscara limpiando strings y evaluando
    mask = df['D_TRANSACTION_TYPE'].astype(str).str.strip().isin(['3']) #['1', '3']

    # Aplicamos el cambio multiplicando directamente la serie enmascarada
    df.loc[mask, 'D_AMOUNT'] = df.loc[mask, 'D_AMOUNT'] * -1

    return df


def clean_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica la categoría de las dos piernas de una transferencia.

    Money Manager parte cada transferencia en tipo ``'3'`` (sale de una
    cuenta) y ``'4'`` (entra en otra), con categorías propias. Bluecoins
    las importa como transferencia, así que categoría y tipo de categoría
    pasan a ``'(Transfer)'``.

    Compara contra los códigos de texto originales. Tiene que ejecutarse
    antes de ``map_transaction_types``, que reemplaza ``'3'`` y ``'4'`` por
    ``'t'``.
    """
    df = df.copy()
    transfer_mask = df['D_TRANSACTION_TYPE'].isin(['3', '4'])
    df.loc[transfer_mask, ['D_CATEGORY', 'D_CATEGORY_TYPE']] = '(Transfer)'
    return df


def map_transaction_types(df: pd.DataFrame) -> pd.DataFrame:
    """Traduce el código de Money Manager al tipo de una letra de Bluecoins.

    Correspondencia usada por el importador:

    * ``0`` ingreso -> ``i``
    * ``1`` gasto -> ``e``
    * ``3`` y ``4`` transferencia -> ``t``

    Cualquier otro código, hoy el único ``'7'`` ("Ingresos", 24.245), no
    está en el diccionario. ``map`` lo deja como nulo y el CSV sale con el
    tipo vacío. El ``fillna(-1)`` solo evita un fallo de casteo; ``-1``
    tampoco tiene letra asignada.
    """
    df = df.copy()

    # 1. Aseguramos que la columna sea numérica entera de forma limpia
    df['D_TRANSACTION_TYPE'] = (
        pd.to_numeric(df['D_TRANSACTION_TYPE'], errors='coerce')
        .fillna(-1)
        .astype(int)
    )

    # 2. Diccionario de mapeo con llaves enteras estables
    type_mapping = {
        0: 'i',
        1: 'e',
        3: 't',
        4: 't'
    }

    # 3. Mapeo seguro
    df['D_TRANSACTION_TYPE'] = df['D_TRANSACTION_TYPE'].map(type_mapping)

    return df


def calculate_exchange_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula ``ZMONEY / D_AMOUNT`` como tasa de cambio hacia la moneda base.

    ``ZMONEY`` es el monto en la moneda principal del libro y ``D_AMOUNT``
    el monto en la moneda de la cuenta. Se usan valores absolutos porque el
    paso anterior ya pudo negativizar las salidas de transferencia, y la tasa
    no debe heredar ese signo.

    Si el monto de la cuenta es 0, la tasa queda en 1.0 para no dividir por
    cero. En cuentas COP contra COP la tasa esperada es 1. En las recargas
    en dólares (seis filas tipo ``'4'`` con centavos) la tasa sale alrededor
    de varios miles de pesos por dólar y no es un entero.
    """
    df = df.copy()

    # 1. Limpieza y tipado estricto de las columnas de entrada
    z_money = np.abs(pd.to_numeric(df['ZMONEY'], errors='coerce').fillna(0.0))
    d_amount = np.abs(pd.to_numeric(df['D_AMOUNT'], errors='coerce').fillna(0.0))

    # 2. Cálculo vectorizado seguro contra división por cero
    exchange_rate = np.where(
        d_amount != 0,
        z_money / d_amount,
        1.0
    )

    # 3. Asignación persistente con tipado float64 explícito
    df['EXCHANGE_RATE'] = exchange_rate.astype(float)

    return df


def clean_text_field(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Deja una columna de texto en una sola línea, sin espacios de más.

    Bluecoins lee un CSV. Un salto de línea dentro de una nota o una
    descripción parte la fila. Esta función cambia saltos y retornos por
    un espacio, colapsa los espacios repetidos y recorta los extremos.
    Un valor nulo pasa a texto vacío y, al final, el vacío vuelve a nulo
    para no exportar comillas sin contenido.

    Si ``column`` no existe, devuelve la copia sin tocarla. El pipeline la
    llama una vez para ``NOTE`` y otra para ``D_DESCRIPTION``.
    """
    df = df.copy()

    if column in df.columns:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.replace(r'[\r\n]+', ' ', regex=True)   # Aplana saltos de línea
            .str.replace(r'\s+', ' ', regex=True)     # Limpia espacios dobles sobrantes
            .str.strip()
        )
        # Opcional: convierte strings vacíos de nuevo a None/NaN
        df[column] = df[column].replace('', None)

    return df


def run_transformation_pipeline(df_raw: pd.DataFrame, timezone: str = "America/Bogota") -> pd.DataFrame:
    """Aplica las limpiezas en el único orden que conserva los códigos de origen.

    Fecha y moneda no dependen del tipo. El signo del monto y la categoría
    ``(Transfer)`` sí leen ``'3'`` y ``'4'``, así que van antes del mapeo a
    ``i`` / ``e`` / ``t``. La tasa va al final porque divide el monto ya
    convertido a float (y, en las salidas, ya con signo).
    """
    df_transformed = (
        df_raw
        .pipe(clean_transaction_date,timezone=timezone)#fecha
        .pipe(clean_currency)#moneda
        .pipe(clean_and_transform_amount)#monto o amount
        .pipe(clean_text_field, column='NOTE')          # Limpia la columna de notas
        .pipe(clean_text_field, column='D_DESCRIPTION')  # Limpia la columna de descripciones
        .pipe(clean_transfers)#categorias
        .pipe(map_transaction_types)#tipo de transaccion
        .pipe(calculate_exchange_rate)#tasa de cambio
    )
    return df_transformed
