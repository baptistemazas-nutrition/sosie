import re
import sys
from pathlib import Path

import markdown

source = Path(sys.argv[1]).read_text(encoding="utf-8")
corps = markdown.markdown(source, extensions=["tables", "fenced_code", "sane_lists", "toc"])
retour = sys.argv[4] if len(sys.argv) > 4 else "mode-emploi.html"
modele = Path(sys.argv[2]).read_text(encoding="utf-8")
style = re.search(r"<style>(.*?)</style>", modele, re.S).group(1)
page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sosie — mode d'emploi complet</title>
<style>{style}
main section h1 {{ font-size: 30px; margin: 0 0 14px; color: var(--bleu); }}
main section h2 {{ margin-top: 30px; }}
main section ul, main section ol {{ padding-left: 22px; }}
main section li {{ margin-bottom: 6px; }}
main section table td:first-child {{ white-space: normal; font-size: 15px; width: auto; }}
main section blockquote {{ margin: 12px 0; padding: 10px 16px; border-left: 4px solid var(--sarcelle); background: var(--sarcelle-clair); border-radius: 10px; }}
.retour {{ display: inline-block; margin-bottom: 18px; }}
</style>
</head>
<body>
<header><div class="contenu"><div><h1>Sosie</h1><p>Mode d'emploi complet</p></div></div></header>
<main><section><a class="retour" href="{retour}">← Mode d'emploi rapide</a>
{corps}
</section></main>
</body>
</html>
"""
Path(sys.argv[3]).write_text(page, encoding="utf-8")
print(len(page))
