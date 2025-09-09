
import os
import re
import time
import html
import requests
import fitz  
from urllib.parse import urlparse, unquote
from requests.exceptions import RequestException

# --- CONFIG ---
PASTA_RAIZ_PROPOSTAS = r'Caminho do Arquivo'

SKIP_IF_EXISTS = True
MAX_RETRIES = 3
RETRY_BACKOFF = 2
MAX_FILENAME_LEN = 120  

# --- Helpers ---
def sanitize_filename(name: str) -> str:
    if not name:
        return ""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', '_', name)    
    name = re.sub(r'\s+', ' ', name)             
    # remove caracteres de controle
    name = ''.join(ch for ch in name if ord(ch) >= 32)
    # remove nomes reservados como "CON", "PRN", ...
    reserved = {"CON","PRN","AUX","NUL"} | {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)}
    base = os.path.splitext(name)[0].upper()
    if base in reserved:
        name = "_" + name
    # remove trailing dots e espaços (Windows não permite)
    name = name.rstrip(' .')
    if not name:
        name = "anexo"
    return name

def truncate_filename(filename: str, max_len: int = MAX_FILENAME_LEN) -> str:
    name, ext = os.path.splitext(filename)
    if len(filename) <= max_len:
        return filename
    # tenta preservar extensão
    ext = ext[:20]  # proteger extensão muito grande (improvável)
    allowed = max_len - len(ext)
    return name[:allowed] + ext

def filename_from_content_disposition(cd: str) -> str | None:
    if not cd:
        return None
    m = re.search(r"filename\*=UTF-8''([^;\n\r]+)", cd)
    if m:
        return unquote(m.group(1).strip(' "\''))
    m = re.search(r'filename="?([^";\n\r]+)"?', cd)
    if m:
        return m.group(1).strip(' "\'')
    return None

def to_long_path(path: str) -> str:
    """
    Converte para formato \\?\C:\... no Windows. Garante absolute path.
    """
    path = os.path.abspath(path)
    if os.name != "nt":
        return path
    if path.startswith('\\\\?\\'):
        return path
    if path.startswith('\\\\'):  # UNC path -> \\?\UNC\server\share\...
        return '\\\\?\\UNC\\' + path.lstrip('\\')
    return '\\\\?\\' + path

def ensure_dir(path: str):
    """
    Tenta criar a pasta, com fallback para usar long path prefix se necessário.
    """
    try:
        os.makedirs(path, exist_ok=True)
        return
    except Exception as e:
        # se Windows, tenta com prefixo long path
        if os.name == "nt":
            try:
                os.makedirs(to_long_path(path), exist_ok=True)
                return
            except Exception as e2:
                raise
        else:
            raise

def safe_print(*args, **kwargs):
    print(*args, **kwargs)

# --- Extração de links (mesmo que antes) ---
def extrair_info_e_link_do_pdf(caminho_pdf):
    try:
        doc = fitz.open(caminho_pdf)
    except Exception as e:
        safe_print(f"  -> ERRO abrindo PDF {caminho_pdf}: {e}")
        return None

    texto_completo = []
    links_encontrados = set()

    try:
        for pagina in doc:
            page_text = pagina.get_text() or ""
            texto_completo.append(page_text)
            try:
                for link in pagina.get_links():
                    uri = link.get('uri') if isinstance(link, dict) else None
                    if uri and 'recurso_mensagem_anexos' in uri:
                        links_encontrados.add(uri.strip())
            except Exception:
                pass
    finally:
        doc.close()

    texto_raw = "\n".join(texto_completo)
    texto_unescaped = html.unescape(texto_raw)
    texto_limpo = re.sub(r'<[^>]+>', ' ', texto_unescaped)
    texto_limpo = texto_limpo.replace('\r', ' ').replace('\n', ' ')
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo)

    for u in re.findall(r'https?://[^\s\'"<>]+', texto_limpo, flags=re.I):
        if 'recurso_mensagem_anexos' in u:
            u = u.rstrip('.,;:)"\'')
            links_encontrados.add(u)

    nome_projeto = None
    identificador = None
    m_nome = re.search(r"NOME\s*DO\s*PROJETO:\s*(.+?)\s*(?:IDENTIFICADOR:|STATUS:|$)", texto_unescaped, flags=re.I|re.S)
    if m_nome:
        nome_projeto = re.sub(r'\s+', ' ', m_nome.group(1)).strip()
    m_id = re.search(r"IDENTIFICADOR:\s*([0-9\-]+)", texto_unescaped, flags=re.I)
    if m_id:
        identificador = m_id.group(1).strip()

    return {
        "nome_projeto": nome_projeto,
        "identificador": identificador,
        "anexo_urls": sorted(links_encontrados)
    }

# --- Download com robustez para Windows long paths ---
def baixar_arquivo(url, pasta_destino, session=None, max_retries=MAX_RETRIES):
    if session is None:
        session = requests.Session()

    parsed = urlparse(url)
    nome_da_url = unquote(os.path.basename(parsed.path)) or None

    attempt = 0
    last_exc = None
    while attempt < max_retries:
        attempt += 1
        try:
            safe_print(f"  -> Tentativa {attempt}: {url[:160]}...")
            resp = session.get(url, stream=True, timeout=30)
            resp.raise_for_status()

            # obtém nome sugerido
            nome = filename_from_content_disposition(resp.headers.get('content-disposition')) \
                   or unquote(os.path.basename(urlparse(resp.url).path)) \
                   or nome_da_url \
                   or f"anexo_{int(time.time())}.bin"

            nome = sanitize_filename(nome)
            nome = truncate_filename(nome, MAX_FILENAME_LEN)
            # remove trailing dots/espaços que geram erro no NTFS
            nome = nome.rstrip(' .')
            if not nome:
                nome = f"anexo_{int(time.time())}.bin"

            # caminho absoluto (sem prefixo ainda)
            pasta_destino_abs = os.path.abspath(pasta_destino)
            # garante que a pasta exista (tenta normal e com long path se precisar)
            try:
                ensure_dir(pasta_destino_abs)
            except Exception as e:
                safe_print(f"    ❌ Erro ao criar pasta '{pasta_destino_abs}': {e}")
                raise

            caminho_final_abs = os.path.join(pasta_destino_abs, nome)

            # verifica existência com caminho normal; se falhar, tenta com long path
            exists_normal = False
            try:
                exists_normal = os.path.exists(caminho_final_abs)
            except Exception:
                exists_normal = False

            # usa caminho longo ao abrir para evitar erro MAX_PATH
            caminho_final_long = to_long_path(caminho_final_abs) if os.name == "nt" else caminho_final_abs

            if SKIP_IF_EXISTS and (exists_normal or (os.path.exists(caminho_final_long) if caminho_final_long != caminho_final_abs else False)):
                safe_print(f"    - Ignorado (já existe): {caminho_final_abs} (len={len(caminho_final_abs)})")
                return True, "skipped", caminho_final_abs

            # escreve usando caminho longo no Windows
            with open(caminho_final_long, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            safe_print(f"    ✅ Salvo: {caminho_final_abs} (len={len(caminho_final_abs)})")
            return True, "downloaded", caminho_final_abs

        except RequestException as e:
            last_exc = e
            safe_print(f"    ❌ Erro na tentativa {attempt}: {e}")
            if attempt < max_retries:
                sleep_for = (RETRY_BACKOFF ** attempt)
                safe_print(f"    -> aguardando {sleep_for}s antes da próxima tentativa...")
                time.sleep(sleep_for)
            else:
                safe_print("    -> máximo de tentativas atingido.")
                return False, f"error: {e}", None

        except Exception as e:
            # debug extra: mostra o caminho e o comprimento quando falha
            try:
                caminho_debug = caminho_final_abs
                safe_print(f"    ❌ Erro inesperado: {e}")
                safe_print(f"    Caminho tentou salvar: {caminho_debug}")
                safe_print(f"    Comprimento do caminho: {len(caminho_debug)}")
                safe_print(f"    Pasta existe? {os.path.exists(os.path.dirname(caminho_debug))}")
            except Exception:
                pass
            last_exc = e
            return False, f"error: {e}", None

    return False, f"error: {last_exc}", None

# --- Execução principal (similar à sua versão) ---
def main():
    if not os.path.isdir(PASTA_RAIZ_PROPOSTAS):
        safe_print(f"ERRO: caminho inválido: {PASTA_RAIZ_PROPOSTAS}")
        return

    session = requests.Session()
    contador_pdfs = contador_links_total = contador_baixados = contador_ignorados = contador_falhas = 0

    for raiz, _, files in os.walk(PASTA_RAIZ_PROPOSTAS):
        for file in files:
            if re.search(r'recursos.*\.pdf$', file, flags=re.I):
                caminho_pdf = os.path.join(raiz, file)
                contador_pdfs += 1
                safe_print(f"\nProcessando PDF: {caminho_pdf}")
                info = extrair_info_e_link_do_pdf(caminho_pdf)
                if not info:
                    safe_print("  -> Não foi possível ler o PDF.")
                    contador_falhas += 1
                    continue

                nome_proj = info.get("nome_projeto") or "(nome não encontrado)"
                ident = info.get("identificador") or "(id não encontrado)"
                urls = info.get("anexo_urls", [])
                safe_print(f"  -> Projeto: {nome_proj} | ID: {ident}")
                if not urls:
                    safe_print("  -> Nenhum link encontrado neste PDF.")
                    continue

                contador_links_total += len(urls)
                safe_print(f"  -> {len(urls)} link(s) encontrados. Iniciando downloads...")

                for url in urls:
                    ok, status, _ = baixar_arquivo(url, raiz, session=session)
                    if ok and status == "downloaded":
                        contador_baixados += 1
                    elif ok and status == "skipped":
                        contador_ignorados += 1
                    else:
                        contador_falhas += 1

    safe_print("\n--- RESUMO ---")
    safe_print(f"PDFs processados: {contador_pdfs}")
    safe_print(f"Links encontrados: {contador_links_total}")
    safe_print(f"Arquivos baixados: {contador_baixados}")
    safe_print(f"Ignorados (já existiam): {contador_ignorados}")
    safe_print(f"Falhas: {contador_falhas}")
    safe_print("--- FIM ---")

if __name__ == "__main__":
    safe_print("--- Iniciando processo (suporte a long paths + truncamento) ---")
    main()
