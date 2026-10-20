"""
ETAPA 1 - Analisa um Reel de referência e extrai o "molde" do vídeo.

Uso (Windows, no terminal):
    pip install yt-dlp faster-whisper imageio-ffmpeg
    python analisar_referencia.py "https://www.instagram.com/reel/DeseulLR2eM/"

Se o Instagram bloquear o download, use os cookies do navegador:
    python analisar_referencia.py URL --cookies-browser firefox
    python analisar_referencia.py URL --cookies cookies.txt

Também aceita um arquivo de vídeo já baixado:
    python analisar_referencia.py reel.mp4

Saída (pasta "analise_referencia"):
    video.mp4          o vídeo baixado
    cenas/             1 quadro por cena (início, meio e fim, para ver zoom/movimento)
    mosaico.jpg        todos os quadros do meio de cada cena numa só imagem
    transcricao.txt    narração transcrita, com tempos
    legendas.srt       narração em formato de legenda
    molde.json         números do molde (duração, cenas, ritmo da fala...)
    relatorio.md       resumo legível
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def achar_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg não encontrado. Instale com:  pip install imageio-ffmpeg")


FFMPEG = achar_ffmpeg()


def rodar_ffmpeg(args):
    r = subprocess.run([FFMPEG, "-hide_banner", *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stderr


def baixar(url, pasta, cookies_browser=None, cookies=None):
    import yt_dlp
    opts = {
        "outtmpl": str(pasta / "video.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": FFMPEG,
        "quiet": False,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies:
        opts["cookiefile"] = cookies
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            caminho = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    except Exception as e:
        print("\nFalha no download:", e)
        print(DICA_COOKIES)
        sys.exit(1)
    meta = {k: info.get(k) for k in ("title", "description", "uploader", "duration")}
    (pasta / "metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return caminho


DICA_COOKIES = """
O Instagram costuma exigir login. Duas saídas:
 1) Feche o navegador e rode com:  --cookies-browser firefox   (ou chrome, edge)
    (No Chrome/Edge recentes isso pode falhar por criptografia; o Firefox é o mais fácil.)
 2) Instale a extensão "Get cookies.txt LOCALLY" (Chrome/Edge/Firefox), entre no
    instagram.com logado, exporte o arquivo cookies.txt e rode com:  --cookies cookies.txt
"""


def duracao(video):
    saida = rodar_ffmpeg(["-i", str(video)])
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", saida)
    h, mi, s = m.groups()
    res = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", saida)
    return int(h) * 3600 + int(mi) * 60 + float(s), (res.groups() if res else None)


def detectar_cortes(video, limiar):
    saida = rodar_ffmpeg(["-i", str(video), "-vf",
                          f"select='gt(scene,{limiar})',showinfo", "-an", "-f", "null", "-"])
    tempos = [float(t) for t in re.findall(r"pts_time:([\d.]+)", saida)]
    # Ignora cortes muito próximos (< 0,4 s), típicos de transições com vários quadros
    filtrados = []
    for t in tempos:
        if not filtrados or t - filtrados[-1] >= 0.4:
            filtrados.append(t)
    return filtrados


def extrair_quadros(video, cenas, pasta):
    pasta.mkdir(exist_ok=True)
    for i, (ini, fim) in enumerate(cenas, 1):
        for rotulo, t in (("a_inicio", ini + 0.1), ("b_meio", (ini + fim) / 2), ("c_fim", fim - 0.15)):
            rodar_ffmpeg(["-y", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
                          "-q:v", "3", str(pasta / f"cena_{i:02d}_{rotulo}.jpg")])


def mosaico(pasta_cenas, destino, n):
    colunas = min(n, 6)
    linhas = (n + colunas - 1) // colunas
    rodar_ffmpeg(["-y", "-start_number", "1", "-i", str(pasta_cenas / "cena_%02d_b_meio.jpg"),
                  "-vf", f"scale=270:-1,tile={colunas}x{linhas}:padding=6:color=white",
                  "-frames:v", "1", str(destino)])


def transcrever(video, modelo):
    from faster_whisper import WhisperModel
    print(f"Transcrevendo com faster-whisper ({modelo})... (1ª vez baixa o modelo)")
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(video), language="pt", word_timestamps=True, vad_filter=True)
    return [{"inicio": s.start, "fim": s.end, "texto": s.text.strip(),
             "palavras": [(w.start, w.end, w.word) for w in (s.words or [])]} for s in segs]


def srt_tempo(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def main():
    ap = argparse.ArgumentParser(description="Analisa um Reel de referência.")
    ap.add_argument("fonte", help="URL do Reel ou caminho de um .mp4")
    ap.add_argument("--saida", default="analise_referencia")
    ap.add_argument("--cookies-browser", help="firefox, chrome, edge...")
    ap.add_argument("--cookies", help="arquivo cookies.txt exportado")
    ap.add_argument("--limiar", type=float, default=0.3,
                    help="sensibilidade da troca de cena (menor = mais cortes)")
    ap.add_argument("--modelo", default="small", help="modelo do whisper: base, small, medium")
    a = ap.parse_args()

    pasta = Path(a.saida)
    pasta.mkdir(exist_ok=True)
    if Path(a.fonte).exists():
        video = Path(a.fonte)
    else:
        video = baixar(a.fonte, pasta, a.cookies_browser, a.cookies)
    print("Vídeo:", video)

    dur, res = duracao(video)
    cortes = detectar_cortes(video, a.limiar)
    limites = [0.0] + cortes + [dur]
    cenas = [(limites[i], limites[i + 1]) for i in range(len(limites) - 1)
             if limites[i + 1] - limites[i] > 0.2]
    extrair_quadros(video, cenas, pasta / "cenas")
    mosaico(pasta / "cenas", pasta / "mosaico.jpg", len(cenas))

    molde = {
        "duracao_s": round(dur, 2),
        "resolucao": "x".join(res) if res else None,
        "num_cenas": len(cenas),
        "tempo_medio_cena_s": round(dur / len(cenas), 2),
        "cenas": [{"n": i, "inicio": round(s, 2), "fim": round(e, 2), "duracao": round(e - s, 2)}
                  for i, (s, e) in enumerate(cenas, 1)],
    }

    try:
        segs = transcrever(video, a.modelo)
    except Exception as e:
        print("Transcrição falhou:", e)
        segs = []
    if segs:
        palavras = [p for s in segs for p in s["palavras"]]
        fala = sum(s["fim"] - s["inicio"] for s in segs)
        molde["narracao"] = {
            "palavras": len(palavras),
            "tempo_falando_s": round(fala, 2),
            "palavras_por_minuto": round(len(palavras) / fala * 60) if fala else None,
            "inicio_fala_s": round(segs[0]["inicio"], 2),
            "fim_fala_s": round(segs[-1]["fim"], 2),
            "texto": " ".join(s["texto"] for s in segs),
        }
        with open(pasta / "transcricao.txt", "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"[{s['inicio']:6.2f} - {s['fim']:6.2f}] {s['texto']}\n")
        with open(pasta / "legendas.srt", "w", encoding="utf-8") as f:
            for i, s in enumerate(segs, 1):
                f.write(f"{i}\n{srt_tempo(s['inicio'])} --> {srt_tempo(s['fim'])}\n{s['texto']}\n\n")
        # Qual frase está em cada cena
        for c in molde["cenas"]:
            c["fala"] = " ".join(s["texto"] for s in segs
                                 if s["inicio"] < c["fim"] and s["fim"] > c["inicio"])

    (pasta / "molde.json").write_text(json.dumps(molde, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    linhas = [
        "# Molde do vídeo de referência", "",
        f"- Duração total: **{molde['duracao_s']} s** ({molde['resolucao']})",
        f"- Número de cenas: **{molde['num_cenas']}**",
        f"- Tempo médio por cena: **{molde['tempo_medio_cena_s']} s**",
    ]
    if "narracao" in molde:
        n = molde["narracao"]
        linhas += [f"- Narração: {n['palavras']} palavras, **{n['palavras_por_minuto']} palavras/min**, "
                   f"de {n['inicio_fala_s']} s a {n['fim_fala_s']} s"]
    linhas += ["", "| Cena | Início | Duração | Fala |", "|---|---|---|---|"]
    linhas += [f"| {c['n']} | {c['inicio']} s | {c['duracao']} s | {c.get('fala', '')} |"
               for c in molde["cenas"]]
    linhas += ["", "Para tipo de imagem, zoom, transições e legendas: compare os quadros "
               "_a_inicio / _b_meio / _c_fim de cada cena em `cenas/` e veja `mosaico.jpg`."]
    (pasta / "relatorio.md").write_text("\n".join(linhas), encoding="utf-8")
    print("\n".join(linhas))
    print(f"\nPronto. Arquivos em: {pasta.resolve()}")


if __name__ == "__main__":
    main()
