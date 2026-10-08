"""Scope of the study, sources and paths, in one place."""

from __future__ import annotations

from pathlib import Path

# 27 federative units, in the order DATASUS uses for file names
UFS = ("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO").split()

# Study period. CNES starts in August 2005, so 2006 is the first full year with
# beds. SINASC is final up to 2024 and preliminary for 2025 (complete months).
FIRST_YEAR = 2006
LAST_FINAL_YEAR = 2024
PRELIM_YEARS = (2025,)
YEARS = tuple(range(FIRST_YEAR, LAST_FINAL_YEAR + 1)) + PRELIM_YEARS

# CNES bed stock is read once a year. December by default, November in 2007
# because SUS neonatal ICU beds vanish from the old code in December 2007
# before reappearing under the new codes (ADR-0003).
BED_MONTH = 12
BED_MONTH_EXCEPTIONS = {2007: 11}


def bed_month(year: int) -> int:
    return BED_MONTH_EXCEPTIONS.get(year, BED_MONTH)


# Neonatal ICU bed codes (CNES LT, CODLEITO). 63 is the untyped code used until
# 2008, 80/81/82 are types I/II/III (ADR-0003).
NICU_CODES = ("63", "80", "81", "82")

# Columns kept from the raw files. Everything is stored as text in the raw
# layer, typing happens downstream.
SINASC_COLUMNS = (
    "CODESTAB",
    "CODMUNNASC",
    "CODMUNRES",
    "LOCNASC",
    "DTNASC",
    "PESO",
    "GESTACAO",
    "SEMAGESTAC",
    "GRAVIDEZ",
    "PARTO",
    "CONSULTAS",
    "IDADEMAE",
)
CNES_LT_COLUMNS = (
    "CNES",
    "CODUFMUN",
    "TP_UNID",
    "TP_LEITO",
    "CODLEITO",
    "QT_EXIST",
    "QT_CONTR",
    "QT_SUS",
    "QT_NSUS",
    "COMPETEN",
)

# DATASUS FTP origin
FTP_HOST = "ftp.datasus.gov.br"
FTP_SINASC_FINAL = "/dissemin/publicos/SINASC/1996_/Dados/DNRES"
FTP_SINASC_PRELIM = "/dissemin/publicos/SINASC/PRELIM/DNRES"
FTP_CNES_LT = "/dissemin/publicos/CNES/200508_/Dados/LT"

# IBGE sources
IBGE_LINKS_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/redes_e_fluxos_geograficos/"
    "ligacoes_rodoviarias_e_hidroviarias/base_de_dados/xls/"
    "Base_de_dados_ligacoes_rodoviarias_e_hidroviarias_2016.xlsx"
)
IBGE_ARRANJOS_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/divisao_regional/"
    "arranjos_populacionais/tabelas_xls_2ed/tab01.xlsx"
)
IBGE_SEATS_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/"
    "localidades/Localidades_do_Brasil/2022/Localidades_Brasil_gpkg.zip"
)
# State boundaries for the map, lowest resolution (IBGE malhas API, 2022)
IBGE_STATES_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&intrarregiao=UF&qualidade=minima&periodo=2022"
)

# Paths, relative to the repository root
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = DATA_DIR / "results"
CACHE_DIR = DATA_DIR / "cache"
MANIFEST = DATA_DIR / "manifest.jsonl"
