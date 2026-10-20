# meu-primeiro-pr
Repositório para praticar o fluxo de Pull Request

## Gerador de Reels – Etapa 1: analisar a referência

```
pip install yt-dlp faster-whisper imageio-ffmpeg
python analisar_referencia.py "https://www.instagram.com/reel/DeseulLR2eM/"
```

Se o Instagram bloquear: `--cookies-browser firefox` ou `--cookies cookies.txt`
(exportado com a extensão "Get cookies.txt LOCALLY").
O resultado fica na pasta `analise_referencia/` (relatorio.md, transcricao.txt, mosaico.jpg, cenas/).
