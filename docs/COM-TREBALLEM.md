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

6. Abans de començar una branca i abans d'obrir el PR: `git fetch` i `gh pr list`. Si un fitxer és en el
   PR obert d'un altre, parla-hi abans de tocar-lo.
7. **Només un bucle de servei (serving loop) alhora per a tot l'equip**: dos bucles enviarien dues
   respostes per petició. Abans d'engegar-ne un, mira el `model_version` més recent a
   `team_02.submissions` i avisa al xat.

## Issues i progrés

Cada carril té el seu issue a GitHub, amb una llista de tasques (GitHub mostra "3 de 7"). L'**issue
índex** (etiqueta `wayfinder:map`) enllaça els quatre, té el que ja hem decidit i el que encara no.

| Carril | Qui | GitHub | Etiqueta |
|---|---|---|---|
| A · Sistema en viu i fiabilitat | Marcel | `MarcelRochera00` | `area:live` |
| B · Model amb l'històric i avaluació offline | Gabriel | `ProGabo` | `area:model` |
| C · Aprenentatge en viu (tendències, feedback, exploració, cold start) | Eudald | `dwakevy` | `area:learning` |
| D · Decisions i relat (anàlisi, dashboard Tukey, pitch, demo) | Miles | `milesgloekler` | `area:decisions` |

- **Problema o idea nova fora de la teva tasca?** No ho arreglis a la teva branca: obre un issue amb
  l'etiqueta del carril, assigna'l a qui toca (o a diversos) i enllaça'l a l'índex. La IA ho sap fer
  (`AGENTS.md`).
- **Una troballa que afecta un altre carril** (com canvia l'estoc, quins clients compren...): comentari a
  l'issue índex i al xat.
- **A cada sincronització**, cadascú deixa un comentari al seu issue: fet / ara / bloquejat. Així
  tothom veu com va cadascú, i si algú s'encalla, qui va avançat l'ajuda o agafa una part. Ho decidim a
  la sincronització.
- Els carrils són flexibles: cadascú aprofundeix en el seu i el pot reorientar si troba una cosa millor.

## Sincronitzacions

Deu minuts, enganxades als àpats (dinar, berenar, sopar, i diumenge a l'esmorzar). L'hora és
orientativa; l'important és anar al dia.

1. Un minut per persona: què hi ha a `main` gràcies a mi, què faré ara, què em bloqueja.
2. Executem `main` des de zero.
3. Contractes i PRs que esperen confirmació.
4. Com anem de puntuació (`docs/experiments.md`).
5. Una línia nova a `docs/pitch.md` i repartiment del bloc següent.

Diumenge abans de les 10:00 deixem en marxa la millor versió; de 10:00 a 12:00 no es toca res llevat
d'una emergència (el llum vermell del leaderboard).

**Recordatori per al sopar:** decidir quin portàtil es queda responent aquesta nit (endollat, sense
suspensió) i qui el vigila.

## Decidit (dissabte 14, alineació)

| Què | Decisió |
|---|---|
| Repte | RawTree · recomanació en temps real (`docs/challenge/brief.md`) + side challenge Tukey (`docs/challenge/side-challenge.md`) |
| Carrils | Taula de dalt; detall a `docs/contracts.md` |
| Qui vigila `main` | Gabriel |
| Idioma | Anglès per a tot el que deixem al repo; la demo, en l'idioma que triem per al jurat |
| Clau de RawTree | Cadascú al seu `.env` local (ignorat per git), copiant `.env.example`; la clau només pel xat privat |
| On corre el sistema | Un portàtil de l'equip per defecte; un servidor al núvol només si cal. Es decideix al sopar |
| Model | Dues capes com a punt de partida flexible: candidats de l'històric + reordenació en viu |
| Validació | Offline amb IPS sobre `history_sessions` + comparació en viu per `model_version`. Mana la de viu |
| Dashboard | Una sola app Streamlit a `app/`: monitorització + Tukey + demo |
