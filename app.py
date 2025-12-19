# -*- coding: utf-8 -*-
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd
import streamlit as st

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(
    page_title="Royal Coffee Estate",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "royal_coffee_system_v5.db"
IMG_PATH = BASE_DIR / "registry_files"
STYLE_PATH = BASE_DIR / "styles.css"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
STATUS_COLORS = {
    "EM LAVOURA / COLHIDO": "#f59e0b",
    "EM SECAGEM": "#f97316",
    "ARMAZENADO": "#22c55e",
    "VENDIDO": "#a3e635",
}

IMG_PATH.mkdir(parents=True, exist_ok=True)


# --- 2. ESTILOS ---
def load_css() -> None:
    if not STYLE_PATH.exists():
        st.warning("Arquivo de estilos não encontrado.")
        return
    css = STYLE_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()


# --- 3. BANCO DE DADOS ---
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query: str, params: Iterable = (), fetch: bool = False):
    try:
        with closing(get_conn()) as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            conn.commit()
            return True
    except sqlite3.Error as e:
        st.error(f"Erro no banco de dados: {e}")
        return None


def fetch_df(query: str, params: Tuple = ()) -> pd.DataFrame:
    try:
        with closing(get_conn()) as conn:
            df = pd.read_sql_query(query, conn, params=params)
        return df
    except sqlite3.Error as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()


def init_db() -> None:
    execute_query(
        """CREATE TABLE IF NOT EXISTS lotes (
        id_lote TEXT PRIMARY KEY,
        data_colheita DATE,
        tipo_colheita TEXT,
        lavoura_origem TEXT,
        status_atual TEXT
    )"""
    )
    execute_query(
        """CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_lote TEXT,
        etapa TEXT,
        data_evento DATE,
        detalhes TEXT,
        info_extra TEXT,
        caminho_foto TEXT
    )"""
    )


init_db()


def refresh_cache() -> None:
    st.cache_data.clear()


@st.cache_data(show_spinner=False)
def load_batches(include_sold: bool = True) -> pd.DataFrame:
    query = "SELECT * FROM lotes"
    params: Tuple = ()
    if not include_sold:
        query += " WHERE status_atual != ?"
        params = ("VENDIDO",)
    query += " ORDER BY data_colheita DESC"
    return fetch_df(query, params)


@st.cache_data(show_spinner=False)
def load_history(batch_id: str) -> pd.DataFrame:
    return fetch_df(
        "SELECT * FROM historico WHERE id_lote=? ORDER BY data_evento DESC, id DESC",
        (batch_id,),
    )


# --- 4. FUNÇÕES AUXILIARES ---
def format_date(value) -> str:
    if pd.isna(value):
        return "-"
    try:
        return pd.to_datetime(value).strftime("%d/%m/%Y")
    except Exception:
        return str(value)


def sanitize_origin(origin: str) -> Tuple[str, str]:
    normalized = re.sub(r"\s+", " ", origin).strip()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized.upper())
    return normalized, slug or "ORIGEM"


def generate_id() -> str:
    year = datetime.now().year
    prefix = f"LOTE-{year}-"
    rows = execute_query(
        "SELECT id_lote FROM lotes WHERE id_lote LIKE ?", (f"{prefix}%",), fetch=True
    )
    max_seq = 0
    if rows:
        for r in rows:
            parts = r[0].split("-")
            if len(parts) >= 3 and parts[2].isdigit():
                seq = int(parts[2])
                max_seq = max(max_seq, seq)
    return f"{prefix}{max_seq + 1:03d}"


def save_media(file, batch_id: str, stage: str) -> str:
    if file is None:
        return ""
    ext = file.name.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        st.warning("Formato de mídia não suportado (use JPG ou PNG).")
        return ""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{batch_id}_{stage}_{ts}.{ext}"
    path = IMG_PATH / filename
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    return str(path)


def record_history(
    batch_id: str, etapa: str, data_evento: str, detalhes: str, info_extra: str = "", caminho: str = ""
) -> None:
    execute_query(
        "INSERT INTO historico (id_lote, etapa, data_evento, detalhes, info_extra, caminho_foto) VALUES (?,?,?,?,?,?)",
        (batch_id, etapa, data_evento, detalhes, info_extra, caminho),
    )


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#94a3b8")
    return f"<span class='chip' style='--chip-color:{color}'>{status}</span>"


def timeline_card(stage: str, event_date: str, batch_id: str, details: str) -> str:
    return f"""
        <div class="history-card">
            <div class="history-card__header">
                <div class="chip" style="--chip-color:#22d3ee;">{stage}</div>
                <div class="history-card__date">{format_date(event_date)}</div>
            </div>
            <div class="history-card__body">
                <div class="history-card__id">{batch_id}</div>
                <div class="history-card__text">{details}</div>
            </div>
        </div>
    """


# --- 5. COMPONENTES DE INTERFACE ---
def sidebar_menu() -> str:
    with st.sidebar:
        if (BASE_DIR / "logo.png").exists():
            st.image(str(BASE_DIR / "logo.png"), use_container_width=True)
        else:
            st.markdown(
                "<div style='font-size:3rem; text-align:center; color:#d4a053; margin:1rem 0;'>☕</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <div style="text-align: center; margin: 0.5rem 0 1.5rem;">
                <h3 style="color: #f1f5f9; margin:0; font-family: 'Playfair Display', serif; font-size:1.5rem;">ROYAL COFFEE</h3>
                <div style="color: #94a3b8; font-size: 0.7rem; letter-spacing: 2px; margin-top:0.25rem;">ESTATE MANAGEMENT</div>
            </div>
        """,
            unsafe_allow_html=True,
        )

        st.divider()

        menu = st.radio(
            "Menu",
            ["Dashboard", "Caderno de Campo", "Processamento", "Comercial", "Rastreabilidade"],
        )

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.caption("v5.1 • Sistema de Gestão")
    return menu


# --- 6. TELAS ---
def show_dashboard() -> None:
    st.markdown("## Visão Geral")
    df = load_batches()

    if df.empty:
        st.info("🌱 Nenhum lote cadastrado. Inicie registrando uma colheita no Caderno de Campo.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Lotes", len(df))
    with col2:
        st.metric("Em Processo", len(df[df["status_atual"] != "VENDIDO"]))
    with col3:
        st.metric("Vendidos", len(df[df["status_atual"] == "VENDIDO"]))

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("### Lotes Recentes")
    recent = df.head(10).copy()
    recent.columns = ["ID do Lote", "Data Colheita", "Tipo Colheita", "Lavoura", "Status"]
    recent["Data Colheita"] = recent["Data Colheita"].apply(format_date)
    recent["Status"] = recent["Status"].apply(status_badge)

    st.markdown(recent.to_html(escape=False, index=False), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Atividades Recentes")

    timeline = fetch_df(
        "SELECT id_lote, etapa, data_evento, detalhes FROM historico ORDER BY data_evento DESC, id DESC LIMIT 8"
    )
    if timeline.empty:
        st.caption("Nenhuma atividade registrada ainda.")
        return

    for _, row in timeline.iterrows():
        st.markdown(timeline_card(row["etapa"], row["data_evento"], row["id_lote"], row["detalhes"]), unsafe_allow_html=True)


def show_fieldbook() -> None:
    st.markdown("## Registro Agrícola")
    tab1, tab2 = st.tabs(["📋 Nova Colheita", "🌿 Manejo"])

    with tab1:
        with st.form("harvest_form", clear_on_submit=True):
            st.markdown("### Criar Novo Lote")
            c1, c2 = st.columns(2)
            dt = c1.date_input("Data da colheita", datetime.now().date())
            origin = c1.text_input("Talhão de origem", placeholder="Ex: Gleba 01, Setor A")
            tipo = c2.selectbox(
                "Método de colheita",
                ["Manual (Derriça)", "Manual (Seletiva)", "Mecânica", "Varrição"],
            )
            foto = c2.file_uploader("Foto (opcional)", type=["jpg", "jpeg", "png"], key="harvest_photo")

            if st.form_submit_button("Criar Lote"):
                origin_text, origin_slug = sanitize_origin(origin)
                if not origin_text:
                    st.error("⚠️ Informe o talhão de origem.")
                else:
                    base_id = generate_id()
                    batch_id = f"{base_id}-{origin_slug}"
                    path = save_media(foto, batch_id, "COLHEITA")
                    execute_query(
                        "INSERT INTO lotes VALUES (?,?,?,?,?)",
                        (batch_id, dt.isoformat(), tipo, origin_text, "EM LAVOURA / COLHIDO"),
                    )
                    record_history(
                        batch_id,
                        "COLHEITA",
                        dt.isoformat(),
                        f"Origem: {origin_text} • {tipo}",
                        caminho=path,
                    )
                    refresh_cache()
                    st.success(f"✅ Lote **{batch_id}** criado com sucesso!")
                    time.sleep(1.5)
                    st.rerun()

    with tab2:
        lotes_df = load_batches()
        if lotes_df.empty:
            st.info("📦 Cadastre uma colheita primeiro na aba 'Nova Colheita'.")
            return

        with st.form("manage_form", clear_on_submit=True):
            st.markdown("### Registro de Insumos e Manejo")
            sel = st.selectbox("Selecione o lote", lotes_df["id_lote"])
            c1, c2 = st.columns(2)
            dt = c1.date_input("Data de aplicação", datetime.now().date(), key="manage_date")
            prod = c2.text_input("Produto/Insumo aplicado", placeholder="Ex: Fertilizante NPK")
            obs = st.text_area(
                "Observações", placeholder="Descrição da aplicação, dosagem, condições climáticas..."
            )
            foto = st.file_uploader("Foto (opcional)", type=["jpg", "jpeg", "png"], key="manejo_foto")

            if st.form_submit_button("Registrar Manejo"):
                if not prod.strip() and not obs.strip():
                    st.error("⚠️ Descreva o produto ou as observações do manejo.")
                else:
                    path = save_media(foto, sel, "MANEJO")
                    detalhes = obs if obs else "Aplicação registrada."
                    record_history(
                        sel,
                        "MANEJO",
                        dt.isoformat(),
                        detalhes,
                        f"Produto: {prod}" if prod else "",
                        caminho=path,
                    )
                    refresh_cache()
                    st.success("✅ Manejo registrado com sucesso!")
                    time.sleep(1)
                    st.rerun()


def show_processing() -> None:
    st.markdown("## Beneficiamento e Processamento")
    lotes_df = load_batches(include_sold=False)

    if lotes_df.empty:
        st.info("📦 Todos os lotes foram vendidos ou não há lotes ativos.")
        return

    sel = st.selectbox("Selecione o lote", lotes_df["id_lote"])
    status = lotes_df.loc[lotes_df["id_lote"] == sel, "status_atual"].values[0]
    st.markdown(f"**Status atual:** {status_badge(status)}", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    t1, t2 = st.tabs(["☀️ Secagem", "📦 Armazenamento"])

    with t1:
        with st.form("dry_form"):
            st.markdown("### Registro de Secagem")
            local = st.radio(
                "Local de secagem",
                ["Terreiro suspenso", "Terreiro chão", "Secador mecânico"],
                horizontal=True,
            )
            dt = st.date_input("Data de início", datetime.now().date(), key="dry_date")
            foto = st.file_uploader("Foto da secagem", type=["jpg", "jpeg", "png"], key="sec_foto")
            if st.form_submit_button("Iniciar Secagem"):
                path = save_media(foto, sel, "SECAGEM")
                record_history(sel, "SECAGEM", dt.isoformat(), f"Local: {local}", caminho=path)
                execute_query("UPDATE lotes SET status_atual=? WHERE id_lote=?", ("EM SECAGEM", sel))
                refresh_cache()
                st.success("✅ Status atualizado: **EM SECAGEM**")
                time.sleep(1)
                st.rerun()

    with t2:
        with st.form("store_form"):
            st.markdown("### Registro de Armazenamento")
            c1, c2 = st.columns(2)
            tulha = c1.text_input("ID Tulha/Galpão", placeholder="Ex: T-01")
            umid = c2.number_input("Umidade (%)", 0.0, 100.0, 11.5, 0.1, format="%.1f")
            dt = st.date_input("Data de armazenamento", datetime.now().date(), key="store_date")
            foto = st.file_uploader("Foto da tulha", type=["jpg", "jpeg", "png"], key="arm_foto")
            if st.form_submit_button("Registrar Armazenamento"):
                if not tulha.strip():
                    st.error("⚠️ Informe o identificador da tulha/galpão.")
                else:
                    path = save_media(foto, sel, "ARMAZENAMENTO")
                    record_history(
                        sel,
                        "ARMAZENAMENTO",
                        dt.isoformat(),
                        f"Tulha: {tulha}",
                        f"Umidade: {umid}%",
                        caminho=path,
                    )
                    execute_query("UPDATE lotes SET status_atual=? WHERE id_lote=?", ("ARMAZENADO", sel))
                    refresh_cache()
                    st.success("✅ Status atualizado: **ARMAZENADO**")
                    time.sleep(1)
                    st.rerun()


def show_commercial() -> None:
    st.markdown("## Expedição e Vendas")
    lotes_df = load_batches(include_sold=False)

    if lotes_df.empty:
        st.success("🎉 Todos os lotes foram vendidos!")
        return

    with st.form("sales_form"):
        st.markdown("### Registrar Venda")
        sel = st.selectbox("Lote a vender", lotes_df["id_lote"])
        c1, c2 = st.columns(2)
        nf = c1.text_input("Nota fiscal", placeholder="Ex: NF-12345")
        cli = c2.text_input("Cliente", placeholder="Nome do comprador")
        dt = st.date_input("Data de saída", datetime.now().date(), key="sale_date")
        foto = st.file_uploader("Foto da NF (opcional)", type=["jpg", "jpeg", "png"], key="venda_foto")

        if st.form_submit_button("Confirmar Venda"):
            if not nf.strip() or not cli.strip():
                st.error("⚠️ Preencha a nota fiscal e o cliente.")
            else:
                path = save_media(foto, sel, "EXPEDICAO")
                record_history(
                    sel,
                    "EXPEDIÇÃO",
                    dt.isoformat(),
                    f"NF: {nf} • Cliente: {cli}",
                    caminho=path,
                )
                execute_query("UPDATE lotes SET status_atual='VENDIDO' WHERE id_lote=?", (sel,))
                refresh_cache()
                st.success(f"✅ Venda registrada! Lote **{sel}** marcado como **VENDIDO**")
                time.sleep(1.5)
                st.rerun()


def show_traceability() -> None:
    st.markdown("## Histórico e Rastreabilidade")
    lotes_df = load_batches()

    if lotes_df.empty:
        st.info("🌱 Nenhum lote cadastrado ainda.")
        return

    search = st.selectbox("Buscar lote", lotes_df["id_lote"].unique())
    lote_info = lotes_df[lotes_df["id_lote"] == search].iloc[0]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", lote_info["status_atual"])
    with col2:
        st.metric("Origem", lote_info["lavoura_origem"])
    with col3:
        st.metric("Colheita", format_date(lote_info["data_colheita"]))

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Linha do Tempo")

    timeline = load_history(search)
    if timeline.empty:
        st.info("📋 Sem histórico para este lote.")
        return

    for _, row in timeline.iterrows():
        with st.container():
            st.markdown(f"#### {row['etapa']}")
            st.caption(f"📅 {format_date(row['data_evento'])}")
            st.markdown(f"**Detalhes:** {row['detalhes'] or 'Sem detalhes.'}")
            if row["info_extra"]:
                st.info(row["info_extra"])
            if row["caminho_foto"] and os.path.exists(row["caminho_foto"]):
                st.image(row["caminho_foto"], use_container_width=True)
            if st.button("🗑️ Remover", key=f"del_{row['id']}", type="secondary"):
                execute_query("DELETE FROM historico WHERE id=?", (row["id"],))
                refresh_cache()
                st.success("Registro removido.")
                time.sleep(0.5)
                st.rerun()
            st.divider()


# --- 7. MAIN ---
def main() -> None:
    menu_choice = sidebar_menu()
    if menu_choice == "Dashboard":
        show_dashboard()
    elif menu_choice == "Caderno de Campo":
        show_fieldbook()
    elif menu_choice == "Processamento":
        show_processing()
    elif menu_choice == "Comercial":
        show_commercial()
    elif menu_choice == "Rastreabilidade":
        show_traceability()


if __name__ == "__main__":
    main()
