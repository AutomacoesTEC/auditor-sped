"""Interface web Flask para o Auditor SPED.

Permite upload dos arquivos ECD, ECF e EFD-Contribuições via browser,
executa a auditoria e exibe os achados com opções de download dos relatórios.
"""

import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Garante que o módulo raiz está no path (para import de main.py, src/, config.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    flash,
    abort,
)
from werkzeug.utils import secure_filename

from main import executar_auditoria, configurar_logging

# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

EXTENSOES_PERMITIDAS = {".txt"}
TAMANHO_MAX_UPLOAD = 500 * 1024 * 1024   # 500 MB

# Diretório temporário isolado para cada sessão de auditoria
_DIR_TEMP_BASE = Path(tempfile.gettempdir()) / "auditor_sped"
_DIR_TEMP_BASE.mkdir(exist_ok=True)

configurar_logging(verbose=False)
logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _extensao_ok(nome_arquivo: str) -> bool:
    return Path(nome_arquivo).suffix.lower() in EXTENSOES_PERMITIDAS


def _salvar_upload(arquivo, dir_saida: Path, prefixo: str) -> Path | None:
    """Salva arquivo enviado de forma segura. Retorna path ou None."""
    if not arquivo or arquivo.filename == "":
        return None
    nome = secure_filename(arquivo.filename)
    if not _extensao_ok(nome):
        return None
    destino = dir_saida / f"{prefixo}_{nome}"
    arquivo.save(str(destino))
    return destino


def _dir_sessao(session_id: str) -> Path:
    """Retorna (e cria) o diretório temporário da sessão."""
    d = _DIR_TEMP_BASE / session_id
    d.mkdir(exist_ok=True)
    return d


def _caminho_seguro(session_id: str, nome: str) -> Path | None:
    """Verifica que o arquivo pertence à sessão (evita path traversal)."""
    base = _DIR_TEMP_BASE / session_id
    alvo = (base / nome).resolve()
    if not str(alvo).startswith(str(base.resolve())):
        return None
    return alvo if alvo.is_file() else None


# ============================================================
# ROTAS
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/auditar", methods=["POST"])
def auditar():
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAX_UPLOAD

    ecd = request.files.get("ecd")
    ecf = request.files.get("ecf")
    # EFD-Contribuicoes desabilitado temporariamente (logica preservada no backend)
    # efd = request.files.get("efd")

    if (not ecd or ecd.filename == "") and (not ecf or ecf.filename == ""):
        flash("Envie pelo menos o arquivo ECD ou ECF.", "erro")
        return redirect(url_for("index"))

    session_id = uuid.uuid4().hex
    dir_sessao = _dir_sessao(session_id)

    caminho_ecd = _salvar_upload(ecd, dir_sessao, "ecd")
    caminho_ecf = _salvar_upload(ecf, dir_sessao, "ecf")
    caminho_efd = None  # EFD temporariamente desabilitado

    limite_valor = float(request.form.get("limite_valor", 0) or 0)
    amostra = int(request.form.get("amostra", 50) or 50)
    gerar_xlsx = "xlsx" in request.form
    gerar_pdf = "pdf" in request.form

    try:
        resultado = executar_auditoria(
            caminho_ecd=str(caminho_ecd) if caminho_ecd else None,
            caminho_ecf=str(caminho_ecf) if caminho_ecf else None,
            caminho_efd=str(caminho_efd) if caminho_efd else None,
            dir_saida=str(dir_sessao),
            limite_valor_gatilho=limite_valor,
            amostra_gatilho=amostra,
            gerar_xlsx=gerar_xlsx,
            gerar_pdf=gerar_pdf,
        )
    except SystemExit:
        flash("Erro: pelo menos um arquivo ECD ou ECF deve ser enviado.", "erro")
        return redirect(url_for("index"))
    except Exception as e:
        logger.exception("Erro durante auditoria da sessão %s", session_id)
        flash(f"Erro ao processar os arquivos: {e}", "erro")
        return redirect(url_for("index"))

    # Descobre nomes dos arquivos gerados
    arquivos_gerados = []
    for arq in dir_sessao.iterdir():
        if arq.suffix in {".xlsx", ".pdf"}:
            arquivos_gerados.append(arq.name)

    return render_template(
        "resultado.html",
        resultado=resultado,
        session_id=session_id,
        arquivos=arquivos_gerados,
    )


@app.route("/download/<session_id>/<nome>")
def download(session_id: str, nome: str):
    # Valida session_id (apenas hex 32 chars)
    if not (len(session_id) == 32 and session_id.isalnum()):
        abort(400)

    arq = _caminho_seguro(session_id, nome)
    if arq is None:
        abort(404)

    return send_file(str(arq), as_attachment=True, download_name=nome)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
