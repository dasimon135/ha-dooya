# HACF — réponse aux messages #17, #20 et #21 (code tournant / hubs Dooya)

> ⚠️ **NON PUBLIÉ.** Décision du 2026-08-23 : on ne répond pas sur HACF pour
> l'instant. Le texte et surtout les sources vérifiées ci-dessous restent
> valables si on change d'avis ou si quelqu'un relance le fil.

> Cible : <https://forum.hacf.fr/t/integration-ha-dooya-pilotez-vos-volets-stores-rf433-dooya-et-clones-depuis-ha-via-esphome-et-cc1101>
>
> Trois messages en attente, tous sur le même sujet :
> - **#17 @schmidtini** (17/07) — pergola GreenOutside, télécommande sans
>   bascule D/K, `dump: raw` confirme le code tournant. « On est piégés. »
> - **#20 @fabrice_lorthios** (22/07) — le SAV GreenOutside dit travailler sur
>   la domotisation, sans plus.
> - **#21 @fabrice_lorthios** (23/07) — « Quelqu'un a-t-il testé les hubs
>   officiels type DD1554 / DD7002B ? » — **sans réponse depuis un mois.**
>
> Poster en réponse à #21, en citant @schmidtini et @fabrice_lorthios.
>
> Sources vérifiées avant rédaction :
> - liste officielle des ponts supportés par l'intégration Motionblinds :
>   <https://www.home-assistant.io/integrations/motion_blinds/>
>   (« DD7002B Connector bridge », « D1554 Connector mini-bridge » — noter
>   l'orthographe **D1554**, pas DD1554)
> - retours d'expérience code tournant + montage optocoupleur :
>   <https://community.home-assistant.io/t/motionblinds-integration-dooya-motors-wintec-dd7006-box-rolling-code/915005>
>   (@dhomeed msg #20 pour les ponts testés, #43 et #46 pour le montage)

---

Salut @fabrice_lorthios, salut @schmidtini,

Désolé pour le délai, la question des hubs méritait mieux qu'une réponse au
jugé. J'ai creusé, et il y a une bonne et une mauvaise nouvelle.

## Les hubs officiels : oui, ils marchent avec Home Assistant

Les deux références que tu cites sont bien dans la liste officielle des ponts
supportés par l'intégration **Motionblinds** de Home Assistant (intégration
native, pas un custom component) :

- **DD7002B** — « Connector bridge »
- **D1554** — « Connector mini-bridge » (attention, la doc HA l'écrit avec
  **un seul D** : `D1554`)

Donc sur le papier c'est propre : pont Wi-Fi, pilotage local, et surtout la
position réelle remontée par le moteur — ce que mon montage CC1101 ne saura
jamais faire, puisque le protocole D est à sens unique.

Il faut récupérer une clé API de 16 caractères dans l'appli constructeur
(Connector / Brel Home / Motion selon le revendeur), et laisser passer le
multicast UDP entre le pont et Home Assistant. Les deux points sont documentés
sur la page de l'intégration :
<https://www.home-assistant.io/integrations/motion_blinds/>

## La mauvaise nouvelle, et elle vous concerne tous les deux

Ces ponts émettent en 433 MHz, exactement comme mon ESP32. Ils ne savent donc
piloter que ce que leur radio sait parler — et pour les moteurs récents en code
tournant, ça ne suit pas non plus.

Il y a un fil anglophone où un utilisateur a fait le tour de la question avec
des moteurs code tournant (télécommande DC2702D, même famille que ta DC2762M
@schmidtini). Il a essayé le **DD7002B**, le **DD7006**, le **DD7006M** et un
Bond Home : aucun ne s'appaire. Son revendeur a fini par lui répondre que Dooya
lui-même n'a pas de pont compatible avec ces moteurs :

<https://community.home-assistant.io/t/motionblinds-integration-dooya-motors-wintec-dd7006-box-rolling-code/915005/20>

Donc @fabrice_lorthios : avant de commander quoi que ce soit pour ta pergola
GreenOutside, fais-toi confirmer par écrit par le vendeur que le pont s'appaire
avec **ta référence moteur exacte**, ou achète chez quelqu'un qui reprend. Le
risque de mettre 80 € dans une boîte qui ne verra jamais tes moteurs est réel.

Et vu ce que t'a répondu leur SAV — « on étudie une façon de domotiser, ce
n'est pas encore au point » — je pense qu'ils sont exactement sur ce mur-là.

## Le plan B qui marche vraiment, et qui coûte 10 €

Là je change complètement d'approche, et honnêtement c'est ce que je ferais à
votre place aujourd'hui.

Puisqu'on ne sait pas parler le code tournant : **on ne le parle pas, on fait
appuyer une vraie télécommande.**

Le montage tient en une phrase : un ESP32 sous ESPHome, des optocoupleurs
soudés sur les pastilles des boutons d'une télécommande d'origine, et la
télécommande alimentée directement sur le 3,3 V de l'ESP32. Home Assistant
« appuie » électriquement sur les boutons. C'est la télécommande qui gère le
code tournant — donc ça marche avec n'importe quel protocole, K compris, sans
rien avoir à décoder.

Comptez une dizaine d'euros de matériel : un ESP32 (~4 €), un module
optocoupleur PC817 8 canaux (~5 €), un peu de fil à wrapper, et une
télécommande de rechange. Le montage complet, photos à l'appui, est décrit dans
le même fil :

- version relais : <https://community.home-assistant.io/t/motionblinds-integration-dooya-motors-wintec-dd7006-box-rolling-code/915005/43>
- version optocoupleurs, plus propre et sans clic : <https://community.home-assistant.io/t/motionblinds-integration-dooya-motors-wintec-dd7006-box-rolling-code/915005/46>

Ce qu'on y gagne : local, pas de cloud, pas d'appli, et une télécommande
multicanal couvre plusieurs volets d'un coup — pour une pergola avec sa
télécommande à canaux, c'est très bien dimensionné.

Ce qu'on y perd, et je préfère le dire : pas de retour de position (comme
ha-dooya, la position reste estimée), pas d'apprentissage automatique, et il
faut sortir le fer à souder. Ce n'est pas élégant. Mais ça fonctionne, c'est
réversible, et ça ne dépend d'aucun bon vouloir de Dooya.

## Une troisième piste, à vérifier sur vos moteurs

Si votre moteur a une **prise RJ-11** (petit connecteur téléphone, sur la tête
du moteur), il existe un module Dooya **DC1545R** en **Zigbee**, à ~11 €. Un
utilisateur du même fil confirme qu'il s'appaire directement dans
Zigbee2MQTT — position réglable au pourcentage, réponse instantanée, aucun
cloud. Il existe aussi en version Wi-Fi/Tuya (**DC1545V**), nettement moins
intéressante.

Le piège : beaucoup de moteurs vendus aujourd'hui sont « RF pure » et n'ont pas
cette prise. Donc avant d'acheter, ouvrez le coffre et regardez la tête du
moteur.

## Et pour ha-dooya ?

Je reste franc sur le périmètre : ha-dooya pilote le protocole D (code fixe), et
ça ne changera pas — décoder du code tournant sans l'algorithme constructeur,
ce n'est pas un week-end de travail, c'est un autre projet.

En revanche votre discussion a de la valeur pour les suivants : je vais ajouter
au tutoriel une section « mon moteur est en code tournant, que faire » qui
reprend les trois pistes ci-dessus, parce que vous êtes visiblement de plus en
plus nombreux dans ce cas et que l'information est éparpillée sur trois forums.

@schmidtini, merci d'avoir fait le test en `dump: raw` jusqu'au bout — c'est
grâce à ça qu'on a un diagnostic sûr plutôt qu'une intuition, et ça a servi à
plus de monde que toi.

Tenez-nous au courant si l'un de vous tente le montage optocoupleur, je suis
preneur du retour.
