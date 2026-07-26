# Message de suivi HACF — v0.8.0

> À poster en réponse dans le fil `[Integration] ha-dooya`.
> Fait suite au message d'annonce de la v0.6.1 : ne réexplique donc ni la carte
> Lovelace, ni l'assistant de calibration, ni le canal 0, ni le multi-nœuds,
> déjà couverts là-bas. Couvre v0.6.2 → v0.8.0.

---

Salut à tous 👋

Petit point depuis l'annonce de la v0.6.1. Pas de nouveauté cette fois, plutôt de la fiabilité — mais il y a deux ou trois choses que vous avez intérêt à connaître.

D'abord, **v0.6.2** : un bug bien vilain m'a été remonté ici même juste après la v0.6.1. Toutes les entités de l'intégration se retrouvaient grisées, « no longer provided ». La cause était un appareil tiers dont les identifiants n'avaient pas tout à fait la forme que je supposais dans le code de suivi de disponibilité — donc impossible à reproduire chez moi. Le traceback collé dans le fil m'a permis de comprendre en dix minutes. Merci encore 🙏, et si vous étiez restés en 0.6.0 ou 0.6.1 sans comprendre, c'était ça.

Ensuite **v0.7.0**, une passe de qualité sans changement visible, et surtout **v0.8.0** qui vient de sortir.

## La v0.8.0

J'ai repris l'intégration à froid, en mode chasse aux bugs. J'en ai trouvé quatre, tous reproduits dans un banc de test avant d'être corrigés — pas juste supposés en relisant le code, parce que je me suis fait avoir une fois en croyant tenir un bug qui n'en était pas un.

Le plus vicieux : **le code de contrôle n'arrivait jamais dans la trame RF**. La valeur était bien stockée, mais plus jamais relue derrière. Le champ « Code de contrôle » de la saisie manuelle ne servait donc strictement à rien. Et le pire, c'est que le mode apprentissage, lui, lit correctement le vrai code sur votre télécommande. Donc si vous aviez une télécommande dont ce code diffère du code bouton, elle était apprise juste puis émise faux — et ça ressemble à un problème de portée RF, pas à un bug logiciel. Bon courage pour le dépannage. Le code est maintenant dérivé du bouton.

⚠️ Conséquence directe : **le champ « Code de contrôle » disparaît des écrans de configuration**. Comme il n'avait aucun effet, rien ne change pour vos volets et vous n'avez rien à reconfigurer.

Celui que vous remarquerez sans doute le plus au quotidien : **lire l'état d'un volet pouvait perturber son mouvement**. Concrètement, sur un « mettre à 50 % », la commande STOP pouvait passer à la trappe et le volet filait jusqu'en butée.

Les deux autres sont plus discrets. **Un même volet pouvait être ajouté deux fois** : rien ne l'empêchait, et les deux entrées se disputaient ensuite la position en permanence, chacune prenant les émissions de l'autre pour un appui sur la télécommande. Et **les identifiants trop longs** étaient acceptés puis tronqués en silence, donc le nœud émettait un identifiant différent de celui affiché à l'écran.

Côté tests, on est passé des 40 dont je parlais dans mon message précédent à 77, avec de la couverture ajoutée là où il n'y en avait pas : l'assistant de calibration, le filtre anti-écho, la resynchronisation quand on utilise la télécommande physique, et la restauration après redémarrage.

## Pour mettre à jour

Via HACS puis redémarrage, c'est tout. **Rien à toucher côté ESPHome**, le contrat entre l'intégration et le nœud n'a pas changé. Pas besoin non plus de recréer ni de reconfigurer vos volets.

Pour ceux qui suivaient : la demande d'inclusion au store HACS par défaut est toujours en attente côté mainteneurs. En attendant, c'est toujours via « Dépôts personnalisés ».

Et si vous tombez sur un bug, n'hésitez vraiment pas — la v0.6.2 est là pour rappeler qu'un traceback bien collé vaut de l'or. 🙌
