"""Leçons texte du chapitre « La conduite », organisées exactement comme le sommaire du livre de code
de la route : une section par sous-chapitre, une leçon par sujet. Contenu adapté au contexte ivoirien
(mêmes règles que les cours existants : vitesses, catégories de permis, taux d'alcool) — les notions
propres à la réglementation française non applicables en Côte d'Ivoire sont signalées comme telles
plutôt que d'être reprises telles quelles.

Utilisé par la commande `seed_course_conduite`. Chaque leçon est un paragraphe de texte (HTML simple).
"""

SECTIONS = [
    ("La vitesse", [
        ("Les règles de circulation",
         "<p>La vitesse est l'un des premiers facteurs d'accident : elle doit toujours être adaptée aux conditions de circulation "
         "(état de la route, trafic, visibilité, météo), même lorsqu'elle respecte la limite affichée. Conduire « trop vite » peut "
         "donc être sanctionné même en dessous de la limitation, si la vitesse n'était pas adaptée aux circonstances.</p>"),
        ("La vitesse",
         "<p>La vitesse maximale autorisée dépend du type de véhicule et du type de route : agglomération, route hors agglomération, "
         "autoroute (voir le cours « Vitesses maximales autorisées » pour le tableau complet). Un conducteur doit connaître ces limites "
         "et les respecter, qu'elles soient rappelées par un panneau ou non.</p>"),
        ("Jeunes conducteurs",
         "<p>Dans certains pays, les nouveaux titulaires du permis sont soumis, pendant une période probatoire, à des limitations de "
         "vitesse réduites et à un nombre de points réduit sur leur permis. <b>Ce dispositif n'existe pas en Côte d'Ivoire</b> : un "
         "nouveau titulaire du permis doit cependant redoubler de prudence, l'expérience de conduite réduisant fortement le risque "
         "d'accident durant les premières années.</p>"),
        ("Non-respect des limitations de vitesse",
         "<p>Rouler au-delà de la vitesse autorisée est un délit ou une contravention selon l'ampleur du dépassement : il expose à une "
         "amende, à une immobilisation du véhicule, voire à une suspension du permis en cas de récidive ou d'excès important, en plus "
         "d'augmenter fortement le risque et la gravité d'un accident.</p>"),
        ("Signalisation",
         "<p>Un panneau rond à fond blanc et à bordure rouge, avec un nombre, indique la vitesse maximale autorisée à cet endroit. "
         "Un panneau identique barré d'un trait gris indique la fin de cette limitation : on revient alors à la limite générale "
         "applicable au type de route parcouru.</p>"),
        ("Réduction de la vitesse",
         "<p>Il faut réduire sa vitesse chaque fois que les circonstances l'exigent : entrée en agglomération, virage, intersection, "
         "chaussée glissante ou rétrécie, présence de piétons ou d'enfants, mauvaise visibilité, véhicule chargé ou tractant une "
         "remorque. Un bon conducteur anticipe ces situations avant d'y être brutalement confronté.</p>"),
        ("Temps de réaction",
         "<p>Le temps de réaction est le temps écoulé entre la perception d'un événement (obstacle, feu qui passe au rouge...) et le "
         "déclenchement de l'action du conducteur (freinage, évitement). Il est allongé par la fatigue, l'alcool, l'âge ou la "
         "distraction (téléphone), et représente une part importante de la distance parcourue avant l'arrêt du véhicule.</p>"),
        ("Distance de sécurité, de freinage et d'arrêt",
         "<p>La <b>distance de sécurité</b> est l'intervalle minimal à conserver avec le véhicule qui précède. La <b>distance de "
         "freinage</b> est la distance parcourue pendant que les freins dissipent l'énergie du véhicule ; elle dépend de la vitesse, "
         "du chargement et de l'adhérence, et elle est environ multipliée par quatre si la vitesse double. La <b>distance d'arrêt</b> "
         "additionne la distance parcourue pendant le temps de réaction et la distance de freinage.</p>"),
        ("Véhicules équipés de pneus à crampons",
         "<p>Dans les pays à climat froid, des pneus à crampons ou pneus neige/hiver peuvent être utilisés en saison hivernale pour "
         "améliorer l'adhérence sur neige et verglas, en respectant des règles particulières de circulation (souvent une vitesse "
         "maximale réduite). <b>Cette notion n'est pas applicable en Côte d'Ivoire</b>, au climat tropical.</p>"),
    ]),
    ("Intersection et priorité", [
        ("L'intersection",
         "<p>Une intersection est un lieu de jonction de deux routes ou plus. Elle peut être réglée par une signalisation (panneaux, "
         "feux, agent) ou, en son absence, par la règle de la priorité à droite. Aborder une intersection impose de ralentir, "
         "d'avertir, de sélectionner sa voie, de vérifier que la voie à traverser est libre et d'observer la règle de priorité "
         "applicable (méthode R.A.S.V.O.).</p>"),
        ("La signalisation de priorité",
         "<p>La priorité à une intersection peut être fixée par un panneau (stop, cédez le passage, losange jaune de route "
         "prioritaire), par un feu tricolore, ou par un agent réglant la circulation. En cas de signalisation contradictoire, "
         "l'ordre de priorité est toujours : agent, puis feux, puis panneaux.</p>"),
        ("La priorité à droite",
         "<p>En l'absence de toute signalisation, la règle de la priorité à droite s'applique : chaque conducteur cède le passage aux "
         "véhicules venant de sa droite. C'est la règle par défaut à une intersection de deux routes de même importance.</p>"),
        ("Les routes prioritaires",
         "<p>Une route prioritaire est annoncée par un panneau losange à fond jaune ; elle conserve sa priorité à chaque intersection "
         "suivante jusqu'au panneau de fin de priorité. Cette priorité se perd néanmoins à l'entrée d'une agglomération, sauf si le "
         "panneau de priorité est répété sur le même support que le panneau d'entrée d'agglomération.</p>"),
        ("La priorité ponctuelle",
         "<p>La priorité ponctuelle est accordée pour un seul carrefour par un panneau « cédez le passage » ou « stop », sans se "
         "prolonger aux intersections suivantes comme le ferait une route prioritaire continue.</p>"),
        ("Le stop",
         "<p>Le panneau stop impose de marquer un arrêt total et net, même en l'absence de tout autre véhicule visible, avant de céder "
         "le passage aux usagers venant de droite comme de gauche. Ne pas marquer l'arrêt à un stop est une infraction grave.</p>"),
        ("Cédez le passage",
         "<p>Le panneau « cédez le passage » impose de laisser passer les véhicules venant de droite comme de gauche, sans obliger à "
         "un arrêt total si la voie est dégagée et que la manœuvre peut se faire en toute sécurité.</p>"),
        ("Carrefour à sens giratoire",
         "<p>Dans un rond-point, le terre-plein central est infranchissable. Sans signalisation particulière, la priorité à droite "
         "s'applique à l'entrée du rond-point. Avec un panneau « cédez le passage au rond-point », ce sont les véhicules qui "
         "souhaitent y entrer qui doivent céder le passage à ceux qui y circulent déjà (lesquels ne peuvent venir que de la gauche).</p>"),
        ("Les feux tricolores",
         "<p>Vert : passage autorisé. Jaune fixe : arrêt obligatoire, sauf si l'arrêt en sécurité est impossible. Rouge : arrêt "
         "obligatoire. Rouge clignotant (feu isolé) : arrêt absolu (passage à niveau, pont mobile, caserne de pompiers). Jaune "
         "clignotant seul : simple prudence, sans changer la règle de priorité habituelle.</p>"),
        ("Les feux avec signalisation",
         "<p>Quand un feu fonctionne normalement, on ne tient pas compte du panneau de priorité placé au même endroit : seul le feu "
         "s'applique. Si les feux sont éteints ou clignotent en jaune, on applique alors le panneau présent ; en l'absence de "
         "panneau, c'est la priorité à droite qui reprend ses droits.</p>"),
        ("Véhicules d'urgence et véhicules prioritaires",
         "<p>Les véhicules de police, gendarmerie, pompiers et SAMU ne sont pas soumis aux limitations de vitesse en intervention. Dès "
         "qu'ils utilisent leurs avertisseurs sonores ou lumineux spéciaux, tout conducteur doit faciliter leur passage : ralentir, "
         "voire s'arrêter et se ranger si nécessaire.</p>"),
        ("Autres cas",
         "<p>Un véhicule sur rail (tramway) est toujours prioritaire. Face à un passage à niveau à barrière levée, la priorité de "
         "passage s'applique normalement ; barrière descendue ou feu rouge clignotant, l'arrêt est absolu.</p>"),
    ]),
    ("Croisements et dépassements", [
        ("Croisements",
         "<p>Le croisement est le passage de deux véhicules, l'un à côté de l'autre, allant en sens inverse : il faut toujours serrer "
         "à droite. Dans un passage étroit, le véhicule le plus encombrant laisse le passage au plus petit, sauf signalisation "
         "contraire.</p>"),
        ("Sur une chaussée en pente",
         "<p>Lorsque deux véhicules se croisent sur une chaussée en pente trop étroite pour se croiser normalement, le véhicule qui "
         "descend doit s'arrêter le premier. Si une marche arrière est nécessaire, c'est le véhicule le plus léger et le plus "
         "maniable qui l'effectue.</p>"),
        ("Dépassements",
         "<p>Le dépassement est le passage d'un véhicule devant un autre allant dans le même sens ; il s'effectue normalement par la "
         "gauche. Avant de dépasser : vérifier l'absence de danger et l'angle mort, avoir une réserve d'accélération suffisante, "
         "avertir, puis reprendre sa place à droite en laissant un intervalle latéral d'au moins un mètre.</p>"),
        ("Dépassements interdits",
         "<p>Le dépassement est interdit en présence d'une ligne continue ou de lignes accolées, à l'approche d'une intersection sans "
         "priorité claire, dans un virage ou au sommet d'une côte à visibilité réduite, sur un passage à niveau, ou chaque fois qu'il "
         "risque de gêner un véhicule venant en sens inverse, qui précède ou qui suit.</p>"),
        ("Dépassements autorisés",
         "<p>Le dépassement normal (par la gauche) est autorisé partout où aucune interdiction (signalisation verticale, horizontale "
         "ou circonstances) ne s'applique. Un dépassement exceptionnel par la droite n'est permis que dans des cas précis, par "
         "exemple un véhicule qui s'apprête à tourner à gauche.</p>"),
    ]),
    ("L'arrêt et le stationnement", [
        ("Définition de l'arrêt",
         "<p>L'arrêt est l'immobilisation momentanée d'un véhicule, le temps nécessaire à la montée ou à la descente de personnes, ou "
         "au chargement et au déchargement de marchandises, le conducteur restant à proximité pour déplacer le véhicule si besoin.</p>"),
        ("Définition du stationnement",
         "<p>Le stationnement est l'immobilisation d'un véhicule au-delà du temps nécessaire à un arrêt, sur la chaussée ou sur "
         "l'accotement. Un stationnement ininterrompu de plus de 7 jours au même endroit est considéré comme abusif.</p>"),
        ("Stationnement et arrêt dangereux",
         "<p>L'arrêt ou le stationnement est dangereux lorsque la visibilité est insuffisante pour les autres usagers : à "
         "l'intersection, dans un virage, au sommet d'une côte, sur un passage à niveau, dans un tunnel ou à proximité immédiate.</p>"),
        ("Stationnement et arrêt gênants",
         "<p>Sont gênants l'arrêt ou le stationnement sur un trottoir, un passage piéton, une piste cyclable, un emplacement réservé "
         "(pompiers, ambulances, personnes handicapées), un arrêt de bus, ou entre le bord de la chaussée et une ligne continue.</p>"),
        ("Les manœuvres",
         "<p>Pour se garer, trois modes principaux : en épi (en biais par rapport au trottoir), en bataille (perpendiculaire au "
         "trottoir), ou en créneau (parallèle au trottoir, entre deux véhicules). Avant toute manœuvre, il faut vérifier les angles "
         "morts et avertir les autres usagers de son intention.</p>"),
    ]),
    ("L'autoroute", [
        ("Se diriger vers l'autoroute",
         "<p>Les panneaux annonçant une autoroute sont de couleur verte (ou bleue selon les pays). Avant de s'y engager, il convient "
         "de vérifier que son véhicule est autorisé à y circuler : les piétons, cyclistes, cyclomoteurs et véhicules incapables "
         "d'atteindre la vitesse minimale requise en sont exclus.</p>"),
        ("Entrer sur l'autoroute",
         "<p>On entre sur l'autoroute par une bretelle de raccordement, en empruntant la voie d'accélération pour atteindre une "
         "vitesse proche de celle de la circulation avant de s'insérer, sans gêner ni obliger les véhicules déjà présents à ralentir "
         "ou à changer de voie. Tout conducteur qui s'insère doit céder le passage à ceux déjà engagés.</p>"),
        ("Le péage",
         "<p>Certaines autoroutes (comme l'autoroute du Nord à Abidjan) sont à péage : on y règle un droit de passage, en général à "
         "la sortie. Il faut ralentir suffisamment tôt à l'approche de la gare de péage et choisir la voie adaptée à son mode de "
         "paiement.</p>"),
        ("Bretelle de raccordement autoroutière",
         "<p>La bretelle de raccordement relie une route ordinaire à l'autoroute. Elle comprend une voie d'accès, puis une voie "
         "d'accélération (à l'entrée) ou de décélération (à la sortie), qui permettent d'ajuster sa vitesse sans perturber la "
         "circulation sur l'autoroute elle-même.</p>"),
        ("Caractéristiques de l'autoroute",
         "<p>L'autoroute comprend deux chaussées à sens unique séparées par un terre-plein central, plusieurs voies de circulation, "
         "des bandes d'arrêt d'urgence de chaque côté, et aucun croisement à niveau (ni intersection, ni passage à niveau, ni feu "
         "tricolore).</p>"),
        ("Marche normale",
         "<p>En marche normale, on circule sur la voie de droite ; les voies de gauche ne servent qu'au dépassement, qui se fait "
         "toujours par la gauche, jamais par la droite. On augmente la distance de sécurité par rapport à la conduite en ville, les "
         "vitesses étant plus élevées.</p>"),
        ("Manœuvres interdites",
         "<p>Sur autoroute, sont interdits : faire demi-tour (même en traversant une interruption du terre-plein central), faire "
         "marche arrière, s'arrêter ou stationner ailleurs que sur une aire aménagée (sauf nécessité absolue, sur la bande d'arrêt "
         "d'urgence, feux de détresse allumés).</p>"),
        ("Bifurcation",
         "<p>Une bifurcation est un point où l'autoroute se divise en deux directions distinctes. Elle est annoncée par un panneau "
         "spécifique plusieurs centaines de mètres à l'avance : il faut se placer sur la bonne voie bien avant la division.</p>"),
        ("Jonction",
         "<p>Une jonction est un point où une autre autoroute ou voie rapide rejoint celle qu'on emprunte. Les véhicules qui "
         "rejoignent doivent s'insérer sans priorité particulière, en respectant les mêmes règles qu'à une entrée classique.</p>"),
        ("Sorties",
         "<p>La sortie se prépare à l'avance, dès le premier panneau de présignalisation, en se plaçant sur la voie de droite sans "
         "ralentir avant d'être effectivement sur la bretelle de sortie, pour ne pas gêner les véhicules qui continuent sur "
         "l'autoroute.</p>"),
        ("Routes pour automobiles",
         "<p>Certaines voies express (parfois appelées « routes pour automobiles ») ressemblent à une autoroute (chaussées "
         "séparées, pas d'intersection à niveau) sans en avoir toutes les caractéristiques réglementaires ; il faut s'y fier à la "
         "signalisation spécifique, qui peut différer légèrement de celle de l'autoroute.</p>"),
    ]),
    ("La conduite de nuit", [
        ("Généralités",
         "<p>Le risque d'accident est nettement plus élevé la nuit : le champ de vision est réduit à la portée des phares, la "
         "fatigue s'accumule et certains dangers (piétons, animaux, obstacles) sont plus difficiles à repérer.</p>"),
        ("Quelques conseils",
         "<p>Utiliser les feux de croisement en agglomération éclairée ou pour croiser/suivre un véhicule, et les feux de route "
         "ailleurs. Passer des feux de route aux feux de croisement suffisamment tôt pour ne pas éblouir. En cas d'éblouissement par "
         "un véhicule venant en face, regarder le bord droit de la chaussée plutôt que les phares, et ralentir si nécessaire.</p>"),
    ]),
    ("Les intempéries", [
        ("La pluie",
         "<p>Sous la pluie, la distance de freinage peut doubler. On circule en feux de croisement. L'aquaplaning survient quand une "
         "pellicule d'eau sépare les pneus de la chaussée : pour l'éviter, réduire sa vitesse sans freiner brutalement.</p>"),
        ("Le brouillard",
         "<p>Dans le brouillard, on adapte sa vitesse pour que la distance de sécurité reste égale à la distance de visibilité, en se "
         "guidant sur le marquage au sol. On utilise les feux de croisement, complétés si besoin par les feux de brouillard ; les "
         "feux de route sont à proscrire, car ils se reflètent sur les gouttelettes et réduisent encore la visibilité.</p>"),
        ("Le vent",
         "<p>Un vent violent peut déporter un véhicule, surtout les plus légers ou les deux-roues. Il faut redoubler de vigilance lors "
         "des dépassements de poids lourds (effet de souffle) et augmenter les intervalles de sécurité.</p>"),
        ("La neige",
         "<p>La neige rend la chaussée glissante et allonge fortement les distances de freinage ; une neige tassée peut être aussi "
         "dangereuse que le verglas. Il faut réduire sa vitesse, augmenter la distance de sécurité et éviter les manœuvres brusques.</p>"),
        ("Le verglas",
         "<p>Le verglas se forme surtout en plaques isolées, dans les zones abritées du soleil et du vent : ponts, sous-bois, fonds de "
         "vallée. Il est souvent invisible, ce qui le rend particulièrement dangereux.</p>"),
        ("La conduite en montagne",
         "<p>En montée, il faut anticiper les pertes de puissance dans les virages et ne pas hésiter à rétrograder. En descente, on "
         "utilise le frein moteur (rapport inférieur engagé) pour limiter l'échauffement des freins, plutôt que de freiner en continu "
         "sur de longues distances.</p>"),
    ]),
]
