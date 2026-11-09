"""Acceso a datos y cálculo de los 5 KPI. Las páginas solo llaman a estas funciones."""
import os
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://cafeteria:cafeteria2026@localhost:5433/cafeteria")


@st.cache_resource
def motor():
    return create_engine(URL, pool_pre_ping=True)


def consulta(sql: str, **params) -> pd.DataFrame:
    with motor().connect() as c:
        return pd.read_sql(text(sql), c, params=params)


def ejecutar(sql: str, **params) -> None:
    with motor().begin() as c:
        c.execute(text(sql), params)


@st.cache_data(ttl=60)
def catalogos() -> dict:
    return {
        "cafeterias": consulta("SELECT id_cafeteria, nombre FROM cafeteria ORDER BY id_cafeteria"),
        "franjas": consulta("SELECT id_franja, nombre, hora_inicio, hora_fin, es_hora_pico FROM franja_horaria ORDER BY hora_inicio"),
        "rango": consulta("SELECT min(fecha) AS desde, max(fecha) AS hasta FROM pedido").iloc[0].to_dict(),
    }


@st.cache_data(ttl=30)
def pedidos(desde: date, hasta: date, cafeterias: tuple, franjas: tuple) -> pd.DataFrame:
    df = consulta(
        """SELECT * FROM v_pedidos
           WHERE fecha BETWEEN :d AND :h
             AND id_cafeteria = ANY(:c) AND id_franja = ANY(:f)""",
        d=desde, h=hasta, c=list(cafeterias), f=list(franjas))
    for col in ("min_espera_fila", "min_atencion", "min_preparacion", "valor_total"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=30)
def detalle(desde: date, hasta: date, cafeterias: tuple, franjas: tuple) -> pd.DataFrame:
    return consulta(
        """SELECT p.fecha, p.id_cafeteria, f.nombre AS franja, f.es_hora_pico, pr.nombre AS producto,
                  pr.categoria, d.cantidad, d.subtotal
             FROM detalle_pedido d
             JOIN pedido p ON p.id_pedido = d.id_pedido
             JOIN producto pr ON pr.id_producto = d.id_producto
             JOIN franja_horaria f ON f.id_franja = p.id_franja
            WHERE p.fecha BETWEEN :d AND :h AND p.id_cafeteria = ANY(:c) AND p.id_franja = ANY(:f)
              AND p.estado <> 'Abandonado'""",
        d=desde, h=hasta, c=list(cafeterias), f=list(franjas))


def horas_pico_por_dia() -> float:
    fr = catalogos()["franjas"]
    pico = fr[fr.es_hora_pico]
    return sum((pd.Timedelta(str(r.hora_fin)) - pd.Timedelta(str(r.hora_inicio))).total_seconds() / 3600
               for r in pico.itertuples()) or 1.0


def calcular_kpis(df: pd.DataFrame) -> dict:
    """Los 5 KPI con las fórmulas exactas de la sección 10 del documento."""
    if df.empty:
        return {k: None for k in ("kpi1", "kpi2", "kpi3", "kpi4", "kpi5")} | {"llegados": 0, "entregados": 0, "ventas": 0}
    entregados = df[df.estado == "Entregado"]
    atendidos = df[~df.abandono_fila & df.hora_toma_pedido.notna()]
    # KPI 3: horas pico analizadas = días con datos × cafeterías × horas pico por día
    pico = entregados[entregados.es_hora_pico]
    unidades = df.groupby(["fecha", "id_cafeteria"]).ngroups
    horas = unidades * horas_pico_por_dia()

    def media(s):
        return round(float(s.mean()), 2) if len(s) else None

    return {
        "kpi1": media(entregados.min_atencion),
        "kpi2": round(100 * entregados.entregado_correcto.fillna(False).astype(bool).mean(), 2) if len(entregados) else None,
        "kpi3": round(len(pico) / horas, 2) if horas and df.es_hora_pico.any() else None,
        "kpi4": media(atendidos.min_espera_fila),
        "kpi5": round(100 * df.abandono_fila.mean(), 2),
        "llegados": int(len(df)),
        "entregados": int(len(entregados)),
        "ventas": float(df.loc[df.medio_pago.notna(), "valor_total"].sum()),
    }


def kpis_por_dia(df: pd.DataFrame) -> pd.DataFrame:
    filas = [{"fecha": f, **calcular_kpis(g)} for f, g in df.groupby("fecha")]
    return pd.DataFrame(filas)
