# Message de suivi HACF — v0.8.0

> À poster en réponse dans le fil `[Integration] ha-dooya`.
> Fait suite au message d'annonce de la v0.6.1 : ne réexplique donc ni la carte
> Lovelace, ni l'assistant de calibration, ni le canal 0, ni le multi-nœuds,
> déjà couverts là-bas. Couvre v0.6.2 → v0.8.0.
>
> Rédigé sans jargon : le lecteur type est un utilisateur de Home Assistant,
> pas un développeur.

---

Salut à tous 👋

Petit point depuis l'annonce de la v0.6.1. Pas de nouveauté cette fois, plutôt de la fiabilité — mais il y a deux ou trois choses que vous avez intérêt à connaître.

D'abord, **v0.6.2** : un bug bien vilain m'a été remonté ici même juste après la v0.6.1. Toutes les entités de l'intégration se retrouvaient grisées, avec le fameux « n'est plus fournie par l'intégration ». En fait, un appareil d'une autre marque était déclaré dans Home Assistant d'une façon un peu inhabituelle, et la partie qui surveille si le nœud ESPHome est en ligne ne s'y attendait pas. Résultat : tout tombait. Impossible à voir chez moi, puisque ça dépendait de ce qu'il y avait d'autre dans son installation. Il a collé le détail complet de l'erreur dans le fil, et ça m'a suffi pour comprendre en dix minutes. Merci encore 🙏 — et si vous êtes restés en 0.6.0 ou 0.6.1 avec des volets grisés sans comprendre pourquoi, c'était ça.

Ensuite **v0.7.0**, du rangement interne sans rien de visible, et surtout **v0.8.0** qui vient de sortir.

## La v0.8.0

J'ai repris l'intégration à froid, en mode chasse aux bugs. J'en ai trouvé quatre. Pour chacun, je me suis forcé à le refaire arriver pour de vrai avant d'y toucher, plutôt que de me fier à ma lecture du code — et j'ai bien fait, parce que je me suis fait avoir une fois en croyant tenir un bug qui n'en était pas un.

Le plus vicieux : **le code de contrôle n'était jamais envoyé au volet**. Il était bien enregistré quelque part, mais plus jamais ressorti ensuite. Le champ « Code de contrôle » de la saisie manuelle ne servait donc strictement à rien. Et le pire, c'est que la détection automatique, elle, lit correctement le vrai code sur votre télécommande. Donc si vous aviez une télécommande dont ce code n'est pas le même que celui du bouton, elle était détectée juste et pilotée faux. Et ça se manifeste comme un souci de portée radio, pas comme un bug — bon courage pour chercher. Ce code est maintenant calculé tout seul à partir du bouton.

⚠️ Conséquence directe : **le champ « Code de contrôle » disparaît des écrans de configuration**. Comme il ne servait à rien, vos volets ne changent pas de comportement et vous n'avez rien à refaire.

Celui que vous remarquerez sans doute le plus au quotidien : **le simple fait d'afficher l'état d'un volet pouvait le déranger en pleine course**. Concrètement, quand vous demandiez « mets-toi à 50 % », l'ordre d'arrêt pouvait se perdre en route et le volet continuait jusqu'en butée.

Les deux autres sont plus discrets. **Un même volet pouvait être ajouté deux fois** : rien ne l'empêchait, et les deux copies se disputaient ensuite sa position en permanence, chacune prenant les ordres envoyés par l'autre pour un appui sur la télécommande. Et **un identifiant trop long** était accepté puis raccourci en douce, si bien que le nœud pilotait un volet différent de celui affiché à l'écran.

Côté tests, on est passé des 40 dont je parlais la dernière fois à 77. J'en ai surtout ajouté là où il n'y en avait aucun : l'assistant de calibration, le mécanisme qui évite qu'un nœud confonde le signal d'un autre nœud avec un appui sur la télécommande, la remise à jour de la position quand on utilise la télécommande physique, et la reprise après un redémarrage de Home Assistant.

## Pour mettre à jour

Via HACS puis redémarrage, c'est tout. **Rien à toucher côté ESPHome** : la façon dont l'intégration et le nœud se parlent n'a pas bougé. Pas besoin non plus de recréer ni de reconfigurer vos volets.

Pour ceux qui suivaient : la demande d'inclusion au store HACS par défaut est toujours en attente de leur côté. En attendant, c'est toujours via « Dépôts personnalisés ».

Et si vous tombez sur un bug, n'hésitez vraiment pas à le signaler, même si vous n'y comprenez rien : copiez simplement le message d'erreur que Home Assistant affiche dans ses journaux. La v0.6.2 est là pour rappeler que ça vaut de l'or. 🙌
