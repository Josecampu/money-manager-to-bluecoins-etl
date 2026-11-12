"""Extracción de movimientos desde la base SQLite de Money Manager.

Este módulo es la etapa Extract del ETL. Abre ``money_android.sqlite`` en
solo lectura lógica (no escribe en la base), resuelve cuentas, categorías y
etiquetas, y devuelve un DataFrame con una fila por movimiento.

La consulta no filtra por fecha por sí sola. ``extract_raw_transactions``
envuelve esa consulta cuando ``main.py`` pide un rango, para no recorrer el
resultado en Python y para seguir usando parámetros de SQLite (``?``), que
evitan armar fechas dentro del texto SQL.

Supuestos que dependen de esta base concreta:

* ``INOUTCOME.ZDATE`` está en milisegundos Unix.
* ``INOUTCOME.DO_TYPE`` es texto (``'0'``, ``'1'``, ``'3'``, ``'4'`` y, en
  un caso, ``'7'``), no un entero.
* ``ASSETS.groupUid = 3`` es el grupo "Tarjetas de débito". Esas cuentas se
  redirigen a ``cardAssetUid``, la cuenta bancaria real de la tarjeta.
* ``ASSETS.currencyUid`` usa el patrón ``DIVISA_DIVISA`` (por ejemplo
  ``COP_COP``). El código de tres letras lo resuelve ``transform.py``.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, time

import pandas as pd

# Una fila de INOUTCOME puede tener varias etiquetas en TX_TAG. El JOIN
# directo multiplicaría el movimiento. tx_tags las aplana antes.
#
# TD_to_asset reescribe la cuenta solo para tarjetas de débito (groupUid 3)
# que apuntan a un banco. El resto de cuentas conserva assetUid.
QUERY = """

WITH 

    tx_tags AS (
        -- Tags pre-agregados: una fila por transacción, sin multiplicar filas
        SELECT txt.txUid,
            GROUP_CONCAT(t.NAME, ', ') AS tags
        FROM TX_TAG AS txt
        JOIN TAG AS t ON t.uid = txt.tagUid
        GROUP BY txt.txUid
    ),
    
    TD_to_asset AS (
        -- Resuelve una sola vez la cuenta real (tarjeta de débito -> banco)
        SELECT io.*,
            CASE WHEN a.groupUid = 3 AND a.cardAssetUid IS NOT NULL
                    THEN a.cardAssetUid
                    ELSE io.assetUid
            END AS TD_to_asset_uid
        FROM INOUTCOME AS io
        LEFT JOIN ASSETS AS a ON a.uid = io.assetUid
    )
SELECT
    r.DO_TYPE            AS D_TRANSACTION_TYPE,
    r.ZDATE              AS D_TRANSACTION_DATE,
    r.ZCONTENT           AS D_DESCRIPTION,
    r.AMOUNT_ACCOUNT     AS D_AMOUNT,
    asse.currencyUid     AS D_CURRENCY,
    r.ZMONEY,
    r.ctgUid,
    ctg.NAME             AS D_CATEGORY_TYPE,
    sctg.NAME            AS D_CATEGORY,
    r.TD_to_asset_uid AS assetUid,
    ag.ACC_GROUP_NAME    AS D_ACCOUNT_TYPE,
    asse.NIC_NAME        AS D_ACCOUNT_NAME,
    r.ZDATA              AS NOTE,
    tt.tags              AS TAGS
FROM TD_to_asset AS r
LEFT JOIN ZCATEGORY AS sctg ON sctg.uid = r.ctgUid
LEFT JOIN ZCATEGORY AS ctg  ON ctg.uid  = sctg.pUid
LEFT JOIN ASSETS    AS asse ON asse.uid = r.TD_to_asset_uid
LEFT JOIN ASSETGROUP AS ag  ON ag.uid   = asse.groupUid
LEFT JOIN tx_tags   AS tt   ON tt.txUid = r.uid
ORDER BY r.ZDATE DESC, r.txUidTrans ASC, r.DO_TYPE ASC;
"""


def extract_raw_transactions(db_path: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Lee los movimientos y, si hay fechas, se queda con ese rango.

    ``start_date`` y ``end_date`` usan el formato ``YYYY-MM-DD``. El inicio
    es las 00:00:00 de ese día y el fin es el último instante del día, para
    que un movimiento de la fecha límite no quede fuera. Esos límites se
    convierten a milisegundos Unix porque así está guardado ``ZDATE``.

    La conversión usa la zona horaria del equipo que ejecuta el script
    (``datetime.timestamp`` sobre una fecha sin zona). La transformación
    posterior muestra las fechas en ``America/Bogota``. En un equipo en
    Colombia ambas coinciden; en otra zona, el recorte y la hora visible
    pueden desfasarse.

    Cuando hay filtro, la consulta original queda dentro de una CTE y el
    ``WHERE`` se aplica encima. Ese ``SELECT`` externo no repite el
    ``ORDER BY``, así que el orden cronológico de la consulta base no está
    garantizado en la ruta que usa ``main.py``.

    Args:
        db_path: Ruta al archivo ``.sqlite`` exportado por Money Manager.
        start_date: Fecha inicial inclusive, o ``None`` para no acotar.
        end_date: Fecha final inclusive, o ``None`` para no acotar.

    Returns:
        DataFrame con las columnas ``D_*`` de la consulta, más ``ZMONEY``,
        ``ctgUid``, ``assetUid``, ``NOTE`` y ``TAGS``.
    """
    base_query = QUERY.strip().rstrip(";")
    date_conditions = []
    params = []

    if start_date:
        # Inicio del día (00:00:00) en la zona local del proceso.
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        start_ms = int(dt_start.timestamp() * 1000)
        date_conditions.append("D_TRANSACTION_DATE >= ?")
        params.append(start_ms)

    if end_date:
        # Fin del día (23:59:59.999999) para no perder movimientos del límite.
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
        dt_end_max = datetime.combine(dt_end.date(), time.max)
        end_ms = int(dt_end_max.timestamp() * 1000)
        date_conditions.append("D_TRANSACTION_DATE <= ?")
        params.append(end_ms)

    # El filtro vive fuera de la consulta base para no duplicar sus JOIN.
    # SQLite sigue calculando categorías y etiquetas de todo el historial
    # y después descarta filas. Con ~12.500 movimientos el costo es bajo.
    if date_conditions:
        query = f"""
            WITH base_transactions AS ({base_query})
            SELECT * 
            FROM base_transactions 
            WHERE {" AND ".join(date_conditions)}
        """
    else:
        query = base_query + ";"

    # closing cierra la conexión aunque pandas falle al leer.
    with closing(sqlite3.connect(db_path)) as conn:
        return pd.read_sql_query(query, conn, params=params)
