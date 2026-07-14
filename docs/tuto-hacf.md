# Tutoriel HACF - Installer et configurer ha-dooya avec ESPHome

Ce tutoriel explique pas a pas comment piloter des volets, stores ou rideaux motorises Dooya RF433 dans Home Assistant avec l'integration ha-dooya et un noeud ESPHome base sur ESP32 + CC1101.

## Objectif

L'objectif est simple :

- envoyer les commandes Monter / Stop / Descendre depuis Home Assistant
- estimer la position du volet sans capteur physique
- regler un pourcentage d'ouverture directement depuis Home Assistant
- apprendre automatiquement l'identifiant du volet depuis la telecommande physique
- eviter de multiplier les boutons ESPHome, un par action et par volet
- profiter de la carte Lovelace fournie avec l'integration (volet anime, vue compacte)
- mesurer les temps de trajet automatiquement avec l'assistant de calibration
- definir une position favorite et une entite "tous les volets" (canal 0)

## Prerequis

- Home Assistant 2026.5 ou plus recent
- HACS installe
- un noeud ESPHome deja ajoute dans Home Assistant
- un emetteur/récepteur RF433 compatible, en pratique un ESP32 avec CC1101
- l'option Allow service calls activee pour l'integration ESPHome dans Home Assistant

## 1. Installer l'integration dans HACS

1. Ouvrir HACS
2. Aller dans les depots personnalises
3. Ajouter le depot GitHub `https://github.com/dasimon135/ha-dooya` en type `Integration`
4. Installer `Dooya RF Covers`
5. Redemarrer Home Assistant

## 2. Preparer le noeud ESPHome

Le noeud ESPHome joue deux roles : il envoie les commandes RF433 et il aide Home Assistant a apprendre automatiquement l'identifiant du volet.

- exposer une action/service `transmit_dooya` pour l'emission RF433
- publier l'evenement Home Assistant `esphome.dooya_received` quand une trame Dooya est recue

Exemple minimal des blocs utiles :

```yaml
api:
  services:
    - service: transmit_dooya
      variables:
        dooya_id: int
        channel: int
        btn: int
        check: int

remote_receiver:
  dump: dooya
  on_dooya:
    then:
      - homeassistant.event:
          event: esphome.dooya_received
          data_template:
            id: "{{ dooya_id }}"
            channel: "{{ dooya_channel }}"
            button: "{{ dooya_button }}"
            check: "{{ dooya_check }}"
          variables:
            dooya_id: !lambda |-
              char buf[9];
              snprintf(buf, sizeof(buf), "%08X", x.id);
              return std::string(buf);
            dooya_channel: !lambda |-
              return std::to_string(x.channel);
            dooya_button: !lambda |-
              return std::to_string(x.button);
            dooya_check: !lambda |-
              return std::to_string(x.check);
```

Quelques points importants :

- le service doit s'appeler exactement `transmit_dooya`
- la detection automatique depend de l'evenement `esphome.dooya_received`
- si Home Assistant refuse l'appel `homeassistant.event`, verifier que les actions Home Assistant sont bien autorisees pour ce noeud ESPHome

## 3. Verifier que le noeud ESPHome remonte bien dans Home Assistant

Dans Home Assistant :

1. Aller dans Parametres puis Appareils et services
2. Ouvrir l'integration ESPHome du noeud RF433
3. Verifier que les appels de services sont autorises

Quand tout est correctement configure, Home Assistant expose un service du type :

- `esphome.nom_du_noeud_transmit_dooya`

Exemple :

- `esphome.volets_dooya_rf433_transmit_dooya`

## 4. Ajouter un volet dans Home Assistant

1. Aller dans Parametres puis Appareils et services
2. Ajouter l'integration `Dooya RF Covers`
3. Choisir le boitier ESPHome qui enverra les commandes
4. Choisir la methode de configuration

Deux choix sont alors proposes :

- saisie manuelle si vous connaissez deja l'identifiant du volet
- detection automatique si vous voulez le lire depuis la telecommande physique

Dans les deux cas, il faut aussi renseigner :

- le temps d'ouverture complet
- le temps de fermeture complet

Ces deux valeurs servent a estimer la position du volet dans Home Assistant.

## 5. Utiliser le mode apprentissage automatique

Le mode apprentissage ne modifie pas le moteur et ne fait aucun appairage RF.

Il se contente d'ecouter la telecommande physique pour recuperer :

- l'identifiant du volet
- le canal

La procedure est la suivante :

1. Dans le flow de configuration, choisir la detection automatique
2. Appuyer sur le bouton Monter de la telecommande physique
3. Attendre la detection
4. Donner un nom au volet

Une fois la detection terminee, l'integration cree une entite `cover` dans Home Assistant.

## 6. Pilotage au quotidien

Une fois le volet ajoute, Home Assistant envoie les commandes RF433 via le service ESPHome :

- Monter
- Stop
- Descendre

L'integration peut aussi estimer la position actuelle du volet et accepter une consigne intermediaire, par exemple 40 % ou 70 %.

En pratique, plus les temps d'ouverture et de fermeture sont proches de la realite, plus l'estimation sera bonne.

Tu peux ensuite piloter le volet comme n'importe quelle autre entite `cover` dans Home Assistant. Les anciens boutons ESPHome exposes un par un ne sont plus necessaires.

## 7. La carte Lovelace incluse

L'integration embarque sa propre carte de tableau de bord : rien a installer dans HACS frontend, rien a declarer dans les ressources Lovelace. Elle apparait dans le selecteur de cartes sous le nom **Dooya Cover Card**, avec un editeur visuel.

```yaml
type: custom:dooya-cover-card
entity: cover.volet_salon
```

La carte affiche une fenetre animee qui suit la position estimee (cliquer dedans envoie le volet a cette hauteur), les boutons Ouvrir / Stop / Fermer, un slider, des positions predefinies et les raccourcis de recalage.

Pour les tableaux de bord avec beaucoup de volets, une **vue compacte** est disponible (option `view: compact` ou champ "Affichage" dans l'editeur) : une seule ligne avec barre de position cliquable et boutons.

## 8. Recalage, calibration et confiance

Comme il n'y a pas de capteur physique, l'etat reste une estimation. Chaque volet expose maintenant des **boutons** sur sa page d'appareil :

- **Marquer ouvert** / **Marquer ferme** : recale la position a 100 % ou 0 % sans faire bouger le volet
- **Calibrer le temps d'ouverture** / **de fermeture** : l'assistant de calibration (voir ci-dessous)

Les services d'entite `dooya.mark_open`, `dooya.mark_closed` et `dooya.set_known_position` restent disponibles pour les automatisations.

### Assistant de calibration

Plus besoin de chronometre :

1. fermer completement le volet
2. appuyer sur **Calibrer le temps d'ouverture** : le volet monte
3. appuyer sur **Stop** (dans HA ou sur la telecommande) pile quand il est completement ouvert
4. le temps mesure est enregistre automatiquement dans les options (une notification confirme la valeur)
5. refaire la meme chose depuis la position ouverte avec **Calibrer le temps de fermeture**

### Confiance dans la position

L'entite expose deux attributs : `position_confidence` (high / medium / low) et `moves_since_sync`. Chaque mouvement qui s'arrete entre les butees fait deriver un peu l'estimation ; une course complete jusqu'a une butee remet le compteur a zero. Si la confiance passe a `low`, il suffit d'ouvrir ou de fermer completement le volet une fois.

## 9. Position favorite

Dans les options de l'entree (bouton **Configurer**), tu peux definir une **position favorite** (par exemple 30 %). Un bouton *Position favorite* apparait alors sur la page de l'appareil, et une pastille etoile sur la carte : un appui envoie le volet a cette position, comme le bouton favori des vraies telecommandes Dooya.

## 10. Canal 0 : tous les volets d'un coup

Les telecommandes multi-canaux Dooya ont un bouton "tous" qui emet sur le canal 0 : tous les volets appaires executent la commande avec une seule trame RF.

Tu peux creer cette entite dans Home Assistant : ajout manuel avec le canal `0` et l'identifiant de la telecommande. L'entite propose Ouvrir / Stop / Fermer (pas de position, chaque volet bougeant independamment). Ideal pour une automatisation "tout fermer le soir" : une seule trame au lieu d'une par volet.

Bonus : quand le bouton "tous" de la telecommande physique est utilise, l'estimation de position de chaque volet individuel est mise a jour automatiquement.

## 11. Ameliorer la fiabilite RF (repetition)

Le protocole RF433 OOK est unidirectionnel : il n'y a pas d'accuse de reception. Dans un environnement avec des interferences (autres appareils 433 MHz, reseaux Wi-Fi proches), une commande peut parfois ne pas etre recue par le moteur.

Pour corriger ce comportement, l'integration propose un reglage **Nombre de repetitions RF** dans les options du volet :

1. Aller dans Parametres puis Appareils et services
2. Cliquer sur **Configurer** sur l'entree Dooya concernee
3. Modifier le champ **Nombre de repetitions RF** (1 a 3)

| Valeur | Comportement |
|--------|--------------|
| 1 | Emission unique — par defaut, convient a la plupart des installations |
| 2 | Deux emissions espacees de 100 ms — recommande si des commandes sont parfois ratees |
| 3 | Trois emissions — pour les environnements RF tres bruyants |

Ne pas depasser 3 repetitions : certains moteurs Dooya peuvent interpreter une serie trop longue comme une commande de configuration.

## 12. Blueprint d'automatisation solaire

Le depot fournit un blueprint pret a importer (`blueprints/automation/dooya/shutters_sun.yaml`) qui :

- ferme les volets quand le soleil descend sous une elevation configurable
- les ouvre le matin au-dessus d'une elevation donnee (jamais avant une heure choisie)
- en option, les ferme pendant les journees chaudes (capteur de temperature exterieure + seuil) et les rouvre quand ca se rafraichit

Import : Parametres > Automatisations et scenes > Blueprints > Importer un blueprint, avec l'URL du fichier GitHub.

## 13. Depannage rapide

### Le boitier ESPHome n'apparait pas dans le flow

Verifier :

- que le noeud ESPHome est bien connecte a Home Assistant
- que le service `esphome.nom_du_noeud_transmit_dooya` existe
- que les appels de services sont autorises

### La detection automatique ne trouve rien

Verifier :

- que `remote_receiver` est actif
- que `dump: dooya` est bien configure
- que l'evenement `esphome.dooya_received` est bien emis
- que le CC1101 recoit bien la telecommande physique

### La commande ne pilote pas le volet

Verifier :

- l'identifiant du volet
- le canal
- le cablage et la frequence du module RF433

### La position estimee n'est pas bonne

Verifier :

- que les temps d'ouverture et de fermeture sont realistes
- qu'un stop manuel ou telecommande n'a pas interrompu un mouvement sans recalage
- que l'entite a bien ete recalee avec `dooya.mark_open`, `dooya.mark_closed` ou `dooya.set_known_position` si necessaire

## 14. Liens utiles

- Depot GitHub : `https://github.com/dasimon135/ha-dooya`
- Issues : `https://github.com/dasimon135/ha-dooya/issues`