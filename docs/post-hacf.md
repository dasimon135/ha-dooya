# [Integration] ha-dooya - Piloter des volets Dooya RF433 dans Home Assistant avec ESPHome

Bonjour à tous 👋

Je partage un petit projet perso autour de Home Assistant et des volets Dooya RF433.

J'ai mis en ligne une intégration custom qui permet de piloter des volets, stores ou rideaux motorisés Dooya directement depuis Home Assistant, sans passer par le hub Wi-Fi propriétaire. 🙂

Le projet s'appelle `ha-dooya`.

Concrètement, l'intégration permet de :

- créer de vraies entités `cover` dans Home Assistant
- envoyer Monter / Stop / Descendre en RF433
- estimer la position du volet sans capteur physique
- piloter une position intermédiaire directement depuis Home Assistant
- configurer un volet manuellement si on connaît déjà son identifiant
- apprendre automatiquement l'identifiant et le canal à partir de la télécommande physique

La version actuelle repose sur un nœud ESPHome qui expose une action/service `transmit_dooya`, avec un montage RF433 du type ESP32 + CC1101. 🔧

Le mode apprentissage fonctionne maintenant en pratique : le nœud ESPHome publie l'événement `esphome.dooya_received`, Home Assistant récupère les informations de la télécommande, et l'intégration crée ensuite l'entité `cover` correspondante. 🎯

J'ai aussi ajouté une gestion de position estimée basée sur le temps d'ouverture et de fermeture, avec possibilité de recalage manuel si besoin. Ça ne remplace pas un vrai capteur de position, mais dans la pratique ça permet déjà un usage bien plus confortable au quotidien. 🙂

Mise à jour v0.4.0 : un réglage **Nombre de répétitions RF** est maintenant disponible dans les options de chaque volet. Il permet d'envoyer la commande RF 2 ou 3 fois si besoin, avec un petit intervalle entre chaque émission. C'est utile quand le moteur rate parfois une commande à cause d'interférences, tout en gardant le comportement par défaut identique à avant.

L'idée derrière tout ça est surtout d'éviter les bricolages avec une pile de boutons ESPHome pour chaque volet, et d'obtenir au final une intégration plus propre côté Home Assistant.

Le chemin valide à ce jour est :

- Home Assistant
- ESPHome
- ESP32
- CC1101

Le dépôt GitHub est ici :

`https://github.com/dasimon135/ha-dooya`

L'installation se fait via HACS en ajoutant le dépôt comme dépôt personnalisé de type `Integration`. 📦

Si certains veulent tester, je suis preneur de retours, notamment sur :

- d'autres moteurs compatibles Dooya ou OEM
- d'autres télécommandes compatibles
- la procédure ESPHome
- le comportement de la position estimée selon les moteurs

Si besoin, je peux aussi partager un exemple ESPHome minimal et aider à valider un montage. 🙌

Si vous avez du matériel compatible sous la main et envie d'essayer, vos retours m'intéressent vraiment. Merci d'avance 👌