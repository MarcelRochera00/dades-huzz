# Com treballem

Això és una **proposta v0** perquè dissabte no perdem la primera hora muntant coses. La provem fins a
l'hora de dinar de dissabte i llavors canviem el que no ens serveixi.

## Per començar (un cop)

```
git clone https://github.com/ProGabo/dades-huzz && cd dades-huzz
./scripts/setup.ps1      # Windows
sh scripts/setup.sh      # Mac / Linux
```

L'script comprova que tens `git`, `uv` i `gh`, instal·la les dependències i et diu quines skills té
el repo. Totes les IA llegeixen les mateixes regles (`AGENTS.md`) i les mateixes skills
(`.agents/skills/`). Només canvia com les crides:

| Eina | Obrir | Cridar una skill | Comprovar que les veu |
|---|---|---|---|
| Claude Code | `claude` dins la carpeta (accepta "trust this folder") | `/grill-with-docs` | escriu `/` i surten a la llista |
| Cursor | *File > Open Folder* amb el repo, xat en mode **Agent** local (no Cloud/Background) | `/grill-with-docs` | escriu `/` i surten a la llista |
| Codex | `codex` dins la carpeta | `$grill-with-docs` | `/skills` |

A Codex, quan la IA vulgui fer `git push` o `gh pr create` et demanarà permís (necessita xarxa): accepta'l.
A Cursor és possible que cada skill surti dues vegades a la llista; són idèntiques.

## El flux, en 4 passos

| Pas | Què li dius a la IA | Per què |
|---|---|---|
| 1. Alinear | `grill-with-docs` + la tasca | 15 minuts de preguntes estalvien una hora de codi que no era el que volies. |
| 2. Prototip (si cal) | `prototype` | Quan s'ha de veure per decidir (una pantalla, un gràfic). Es llença després. |
| 3. Construir | La IA implementa el pla | Amb una comprovació que passa o falla, la IA sap quan ha acabat. |
| 4. Entregar | `pr-final` | Revisa, executa i obre el PR amb la prova que funciona. |

No cal que recordis la sintaxi: escriure *"grill-with-docs: vull fer X"* també funciona. Si mai la
IA diu que no troba una skill, digues-li: *"llegeix `AGENTS.md` i segueix la skill grill-with-docs"*. Les skills són fitxers a `.agents/skills/` i qualsevol IA les pot llegir.

## Què esperar (perquè no sorprengui)

- **`grill-with-docs` fa moltes preguntes**, per rondes i numerades. Cada una porta una resposta
  recomanada: si hi estàs d'acord, respons "sí". No escriu codi fins que confirmes que esteu
  alineats. Sembla lent i és el que fa que després surti a la primera.
- **Els fets els busca la IA** (mirant el repo o el repte); a tu només et pregunta decisions.
- **`pr-final` pot aturar-se** per preguntar-te si arregles un problema abans d'obrir el PR.
- El PR surt en anglès, amb el que canvia, la prova executada i què pot trencar.

## Per no trepitjar-nos

1. `main` sempre es pot ensenyar. Ningú hi fa commits directes.
2. Cada tasca, una branca curta `nom/tema` i un PR.
3. **El PR el mergeja qui l'ha fet**, quan el CI és verd. Si se n'oblida, el pot mergejar qualsevol.
4. **Confirmació d'algú altre només quan cal de veritat**: si toques el carril d'un altre o un
   contracte (`docs/contracts.md`). Ho poses a la secció *Needs confirmation from* del PR, amb la persona
   i la pregunta concreta. Mentre hi hagi una casella sense marcar, el PR és un esborrany.
5. Integra a `main` com a mínim un cop per bloc de feina.

## Sincronitzacions

Deu minuts, enganxades als àpats (dinar, berenar, sopar, i diumenge a l'esmorzar). L'hora és
orientativa; l'important és anar al dia.

1. Un minut per persona: què hi ha a `main` gràcies a mi, què faré ara, què em bloqueja.
2. Executem `main` des de zero.
3. Contractes i PRs que esperen confirmació.
4. Com anem de puntuació (`docs/experiments.md`).
5. Una línia nova a `docs/pitch.md` i repartiment del bloc següent.

Dissabte al vespre fem una **entrega de prova**. Diumenge a les 10:00 deixem d'afegir coses noves.

## A decidir junts

| Què | Proposta | Decisió |
|---|---|---|
| Repte | El triem després de la presentació | |
| Carrils (qui fa què) | Segons el repte i l'eina de cadascú | |
| Qui vigila `main` i l'entrega | Gabo, si us sembla bé | |
| Idioma del que entreguem | Anglès | |
| Què sobra o què falta d'aquesta pàgina | | |
