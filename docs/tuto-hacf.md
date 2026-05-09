# Tutoriel HACF - Installer et configurer ha-dooya avec ESPHome

Ce tutoriel explique pas a pas comment piloter des volets, stores ou rideaux motorises Dooya RF433 dans Home Assistant avec l'integration ha-dooya et un noeud ESPHome base sur ESP32 + CC1101.

## Objectif

L'objectif est simple :

- envoyer les commandes Monter / Stop / Descendre depuis Home Assistant
- apprendre automatiquement l'identifiant du volet depuis la telecommande physique
- eviter de multiplier les boutons ESPHome, un par action et par volet

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

Tu peux ensuite piloter le volet comme n'importe quelle autre entite `cover` dans Home Assistant. Les anciens boutons ESPHome exposes un par un ne sont plus necessaires.

## 7. Depannage rapide

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

## 8. Liens utiles

- Depot GitHub : `https://github.com/dasimon135/ha-dooya`
- Issues : `https://github.com/dasimon135/ha-dooya/issues`