# Proposition de post forum HACF

Bonjour a tous,

Je partage un petit projet perso autour de Home Assistant et des volets Dooya RF433.

J'ai mis en ligne une integration custom qui permet de piloter des volets, stores ou rideaux motorises Dooya directement depuis Home Assistant, sans passer par le hub Wi-Fi proprietaire.

Le projet s'appelle `ha-dooya`.

Concretement, l'integration permet de :

- creer de vraies entites `cover` dans Home Assistant
- envoyer Monter / Stop / Descendre en RF433
- configurer un volet manuellement si on connait deja son identifiant
- apprendre automatiquement l'identifiant et le canal a partir de la telecommande physique

La version actuelle repose sur un noeud ESPHome qui expose une action/service `transmit_dooya`, avec un montage RF433 du type ESP32 + CC1101.

Le mode apprentissage fonctionne maintenant en pratique : le noeud ESPHome publie l'evenement `esphome.dooya_received`, Home Assistant recupere les informations de la telecommande, et l'integration cree ensuite l'entite `cover` correspondante.

L'idee derriere tout ca est surtout d'eviter les bricolages avec une pile de boutons ESPHome pour chaque volet, et d'obtenir au final une integration plus propre cote Home Assistant.

Le chemin valide a ce jour est :

- Home Assistant
- ESPHome
- ESP32
- CC1101

Le depot GitHub est ici :

`https://github.com/dasimon135/ha-dooya`

L'installation se fait via HACS en ajoutant le depot comme depot personnalise de type `Integration`.

Si certains veulent tester, je suis preneur de retours, notamment sur :

- d'autres moteurs compatibles Dooya ou OEM
- d'autres telecommandes compatibles
- la procedure ESPHome

Si besoin, je peux aussi partager un exemple ESPHome minimal et aider a valider un montage.