# Message de suivi HACF — v0.8.0

> À poster en réponse dans le fil `[Integration] ha-dooya`.
> Le message d'origine (`post-hacf.md`) s'arrêtait à la v0.4.0 : celui-ci fait
> le pont jusqu'à la v0.8.0.

---

Petit point d'étape sur `ha-dooya` 👋

Le fil s'était arrêté à la v0.4.0 et il s'est passé pas mal de choses depuis. Voici l'essentiel, avec la **v0.8.0** qui vient de sortir.

D'abord un grand merci à celui d'entre vous qui m'avait remonté le bug des entités grisées en v0.6.0 : le traceback fourni a permis de corriger en v0.6.2. C'était un appareil tiers dont les identifiants ne rentraient pas dans le format que je supposais, et ça faisait tomber toutes les entités de l'intégration. Typiquement le genre de chose qu'on ne voit pas chez soi. 🙏

## Ce qui est arrivé depuis la v0.4.0

**Une carte Lovelace intégrée** 🎨 — `custom:dooya-cover-card`, livrée avec l'intégration : rien à installer ni à déclarer dans les ressources Lovelace. Volet animé qui suit la position estimée, curseur, raccourcis 0/25/50/75/100 %, éditeur visuel. Trois affichages : complet, compact (une ligne) et tuile. La fenêtre suit même la course du soleil via `sun.sun` — aube, jour, crépuscule, nuit.

**Un assistant de calibration** ⏱️ — fini le chronomètre à la main. Volet en butée, on appuie sur « Calibrer le temps d'ouverture », et on appuie sur STOP au moment exact où il arrive en haut. Le temps mesuré est enregistré tout seul dans les options.

**Des boutons de recalage** sur la page de l'appareil : « Marquer ouvert », « Marquer fermé », et une **position favorite** optionnelle qui fait apparaître un bouton dédié.

**Un indicateur de confiance** — la position étant estimée, chaque arrêt en milieu de course ajoute un peu d'erreur. L'attribut `position_confidence` passe de `high` à `medium` puis `low`, et se remet à zéro dès que le volet atteint une butée.

**Le canal 0 (bouton « tous »)** — les télécommandes multi-canaux Dooya émettent sur le canal 0, exécuté par tous les volets appairés. On peut créer cette entité dans HA : une seule trame RF au lieu d'une par volet pour un « tout fermer le soir ».

**Le multi-nœuds** 📡 — pour les maisons en béton armé, on peut déployer plusieurs nœuds ESPHome et assigner chaque volet au plus proche, depuis les options et sans recréer l'entrée. Un filtre anti-écho évite qu'un nœud en réception prenne la trame émise par un autre pour un appui télécommande.

**Divers** : une alerte de réparation quand le service ESPHome de la passerelle disparaît (nœud hors ligne), une étape de reconfiguration pour corriger l'identité d'un volet sans le recréer, un blueprint d'automatisation volets/soleil, et un panneau de diagnostic.

## La v0.8.0 : une passe de débogage complète

Celle-ci n'apporte pas de fonctionnalité, mais corrige quatre défauts. Chacun a été **reproduit dans un banc de test Home Assistant avant d'être corrigé**, pas juste supposé à la lecture du code.

**Le code de contrôle n'arrivait jamais dans la trame RF.** La valeur était stockée puis jamais relue : le champ « Check code » de la saisie manuelle ne servait à rien. Plus embêtant, le mode apprentissage lit le vrai code de contrôle sur votre télécommande — donc une télécommande dont ce code diffère du code bouton était apprise correctement puis émise faux, et la panne ressemblait à un problème de portée RF. Le code est maintenant dérivé du bouton.

⚠️ **Conséquence visible : le champ « Code de contrôle » disparaît des écrans de configuration.** Comme il n'avait aucun effet, rien ne change pour vos volets et il n'y a rien à reconfigurer.

**Un même volet pouvait être ajouté deux fois.** Rien ne l'empêchait, et les deux entrées se disputaient alors l'estimation de position en permanence, chacune voyant les émissions de l'autre comme un appui télécommande. C'est maintenant bloqué à l'ajout comme à la reconfiguration.

**Les identifiants trop longs étaient acceptés** puis tronqués silencieusement : le nœud émettait un identifiant différent de celui affiché. Désormais refusé avec un message clair.

**Lire l'état d'un volet pouvait perturber son mouvement.** Sur un déplacement partiel (« mettre à 50 % »), la commande STOP pouvait être perdue et le volet continuait jusqu'en butée. C'est le correctif le plus concret au quotidien.

Côté tests, on est passé de 54 à 77, avec une couverture ajoutée sur l'assistant de calibration, le filtre anti-écho, la resynchronisation par télécommande physique et la restauration après redémarrage.

## Pour mettre à jour

Via HACS, puis redémarrage de Home Assistant. **Rien à changer sur le nœud ESPHome** : le contrat entre l'intégration et le nœud n'a pas bougé. Pas besoin non plus de recréer ou reconfigurer vos volets.

## Toujours preneur de retours

Le dépôt : `https://github.com/dasimon135/ha-dooya`

Ce qui m'intéresse particulièrement :

- d'autres moteurs Dooya ou OEM compatibles, et d'autres télécommandes
- le comportement de la position estimée selon les moteurs
- les retours sur la carte Lovelace et l'assistant de calibration
- les configurations multi-nœuds, si certains ont de gros volumes ou des murs difficiles

Et si vous tombez sur un bug, un traceback vaut de l'or — le correctif de la v0.6.2 en est la preuve. 🙌
