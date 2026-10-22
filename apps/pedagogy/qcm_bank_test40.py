"""Test « Code de la route » — 40 questions tirées du chapitre 16 « Questions » / chapitre 17
« Réponses » du livre (docs/code_route.pdf, pages 208-239).

Utilisée par la commande `seed_qcm_test40`. Chaque question : code unique, thème, difficulté,
type (single = une seule bonne réponse, multi = plusieurs bonnes réponses), énoncé, explication
(texte de la page « Réponses » du livre), ses choix (lettre, texte, bonne réponse ou non) et le nom
du fichier photo associé dans apps/pedagogy/qcm_images/ (ou None pour les questions sans photo).

5 des 40 questions du livre (n° 10, 20, 21, 31, 36) sont annoncées par le livre comme
« Question écrite » : contrairement à ce que ce terme laisse penser, ce ne sont PAS des questions
ouvertes à réponse libre — elles ont bien un énoncé, des choix lettrés A/B/(C/D) et une réponse
corrigée au chapitre 17, exactement comme les 35 autres. La seule différence est qu'elles ne sont
pas illustrées par une photo de conduite : le livre affiche à la place un visuel générique
« Question écrite ». Ces 5 questions sont donc conservées comme Question à choix normales,
simplement avec image_path=None (pas de photo).

Pour les 9 questions à deux sous-parties (ex. n°7 : céder le passage à droite ET à gauche), les
4 choix du livre sont conservés tels quels (qtype="multi", 2 ou 3 bonnes réponses) avec le texte
préfixé par la sous-partie concernée pour rester compréhensible hors contexte de la double page du
livre (ex. « Céder le passage à droite : OUI » plutôt que juste « OUI »).

La question n°12 partage sa photo et sa numérotation de choix (C/D) avec la question n°11 sur la
même double page du livre ; ses choix ont été re-lettrés en A/B pour cohérence avec le reste de la
banque (le livre utilise déjà un repère "Réponse A" = premier choix pour cette question en page
réponses, ce qui confirme que la numérotation continue C/D n'était qu'une convention de mise en
page).
"""

QUESTIONS = [
    {"code": "T40-01", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_01.png",
     "text": "Dans cette situation (panneau annonçant deux ou trois virages dangereux, le premier à droite) :",
     "explanation": "Le panneau indique deux ou trois virages dangereux dont le premier est à droite. Je ralentis, la vitesse est limitée à 50 km/h.",
     "choices": [("A", "Je maintiens ma vitesse", False), ("B", "Je ralentis", True), ("C", "J'accélère", False)]},

    {"code": "T40-02", "theme": "code", "difficulty": "medium", "qtype": "multi", "image_path": "question_02.png",
     "text": "Je peux dépasser la voiture rouge :",
     "explanation": "Les dépassements s'effectuent par la gauche. Le dépassement par la droite est interdit sauf quand un véhicule tourne à gauche s'il reste suffisamment de place, ou quand il s'agit d'un tramway circulant au milieu d'une chaussée à double sens. Je maintiens ma vitesse ; en aucun cas je ne dois accélérer.",
     "choices": [("A", "OUI, je peux dépasser", False), ("B", "NON, je ne peux pas dépasser", True),
                 ("C", "Je peux accélérer", False), ("D", "Je maintiens ma vitesse", True)]},

    {"code": "T40-03", "theme": "priority", "difficulty": "medium", "qtype": "multi", "image_path": "question_03.png",
     "text": "Dans cette situation (carrefour sans signalisation particulière, une motocyclette arrive sur la droite) :",
     "explanation": "Dans ce carrefour, sans signalisation particulière, la règle de la priorité à droite s'applique. À droite, une motocyclette arrive mais elle est éloignée de l'intersection et j'ai le temps de passer sans danger. Je passe sans ralentir.",
     "choices": [("A", "Je m'arrête", False), ("B", "Je passe", True),
                 ("C", "Je maintiens ma vitesse", True), ("D", "Je ralentis", False)]},

    {"code": "T40-04", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_04.png",
     "text": "Dans cette situation (panneau de danger annonçant un feu tricolore) : je ralentis.",
     "explanation": "Le panneau de danger m'annonce un feu tricolore. Comme pour tout danger, je ralentis.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-05", "theme": "safety", "difficulty": "hard", "qtype": "single", "image_path": "question_05.png",
     "text": "Je roule à 80 km/h, ma distance de sécurité est suffisante :",
     "explanation": "La distance de sécurité équivaut à la distance parcourue pendant 2 secondes, soit le double du temps de réaction. À 80 km/h, cette distance est d'environ 48 mètres. En mesurant les pointillés du marquage au sol, la distance réellement respectée n'est que d'environ 34 mètres : elle est donc insuffisante.",
     "choices": [("A", "OUI", False), ("B", "NON", True)]},

    {"code": "T40-06", "theme": "code", "difficulty": "easy", "qtype": "single", "image_path": "question_06.png",
     "text": "Je peux dépasser les 2 camions :",
     "explanation": "Je circule sur une chaussée à sens unique, la voie est dégagée à l'arrière et je peux dépasser les deux camions sans danger.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-07", "theme": "priority", "difficulty": "medium", "qtype": "multi", "image_path": "question_07.png",
     "text": "À la prochaine intersection, je dois céder le passage :",
     "explanation": "Ce panneau annonce une intersection où les usagers venant de droite et de gauche doivent me céder le passage. C'est un panneau ponctuel qui ne concerne que la prochaine intersection : je n'ai donc à céder le passage ni à droite ni à gauche.",
     "choices": [("A", "À droite : OUI", False), ("B", "À droite : NON", True),
                 ("C", "À gauche : OUI", False), ("D", "À gauche : NON", True)]},

    {"code": "T40-08", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_08.png",
     "text": "Dans cette situation (panneau de sens interdit en face, flèche bleue obligeant à tourner à droite) :",
     "explanation": "La signalisation m'impose de tourner à droite. La rue en face est interdite (panneau de sens interdit). Le panneau bleu avec une flèche m'oblige à tourner à droite.",
     "choices": [("A", "Je tourne à droite", True), ("B", "Je vais tout droit", False)]},

    {"code": "T40-09", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_09.png",
     "text": "Ce panneau indique la sortie d'une zone à stationnement :",
     "explanation": "Ce panneau indique une sortie de zone à stationnement à durée limitée contrôlée par disque.",
     "choices": [("A", "Payant", False), ("B", "Gratuit", True)]},

    {"code": "T40-10", "theme": "safety", "difficulty": "medium", "qtype": "single", "image_path": None,
     "text": "Le risque de blessures plus graves ou mortelles pour un conducteur est plus élevé s'il est :",
     "explanation": "Les risques de blessures graves ou mortelles sont plus élevés si le conducteur est éjecté de son véhicule. Le port de la ceinture de sécurité est obligatoire pour éviter ce risque : elle évite l'éjection du conducteur en le rendant solidaire de son siège.",
     "choices": [("A", "Retenu par sa ceinture", False), ("B", "Éjecté de son véhicule", True)]},

    {"code": "T40-11", "theme": "code", "difficulty": "easy", "qtype": "single", "image_path": "question_11.png",
     "text": "Je peux dépasser :",
     "explanation": "La voie est dégagée et aucun véhicule ne me dépasse ou n'est sur le point de me dépasser.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-12", "theme": "priority", "difficulty": "medium", "qtype": "single", "image_path": "question_12.png",
     "text": "Comme le véhicule qui me précède, je vais tout droit, à une intersection avec un « STOP » :",
     "explanation": "Je suis à une intersection avec un « STOP », je dois marquer l'arrêt. Le fait que le véhicule qui me précède passe indique que les voies de droite et de gauche sont dégagées, mais je dois impérativement marquer l'arrêt au niveau de la ligne blanche et vérifier que les voies sont dégagées.",
     "choices": [("A", "Je m'arrête", True), ("B", "Je passe sans m'arrêter", False)]},

    {"code": "T40-13", "theme": "signs", "difficulty": "medium", "qtype": "multi", "image_path": "question_13.png",
     "text": "Après cette signalisation, je circule :",
     "explanation": "Ce panneau indique une entrée d'autoroute. Sauf indication contraire, la vitesse y est limitée à 130 km/h (110 km/h pour les conducteurs ayant moins de 2 ans de permis). Ce n'est pas une route pour automobiles.",
     "choices": [("A", "Sur une autoroute : OUI", True), ("B", "Sur une autoroute : NON", False),
                 ("C", "Sur une route pour automobiles : OUI", False), ("D", "Sur une route pour automobiles : NON", True)]},

    {"code": "T40-14", "theme": "safety", "difficulty": "medium", "qtype": "single", "image_path": "question_14.png",
     "text": "Par temps de brouillard, je me guide :",
     "explanation": "Par temps de brouillard, je suis le bord droit de la chaussée en me guidant avec le marquage au sol. Je dois laisser une distance de sécurité plus importante, car le véhicule qui me précède devient visible tardivement.",
     "choices": [("A", "Avec le marquage au sol", True), ("B", "Avec les feux du véhicule qui me précède", False)]},

    {"code": "T40-15", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_15.png",
     "text": "Je peux stationner à droite :",
     "explanation": "Le marquage au sol indique une zone de stationnement.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-16", "theme": "signs", "difficulty": "hard", "qtype": "multi", "image_path": "question_16.png",
     "text": "Dans cette situation (feux tricolores en forme de flèches) :",
     "explanation": "Les feux en forme de flèches s'appliquent aux voies et directions auxquelles ils sont associés. Le feu rouge concerne la voie de gauche qui tourne à gauche. Le feu vert concerne ma voie qui va tout droit : je passe sans m'arrêter.",
     "choices": [("A", "Je passe au feu vert : OUI", True), ("B", "Je passe au feu vert : NON", False),
                 ("C", "Je m'arrête au feu rouge : OUI", False), ("D", "Je m'arrête au feu rouge : NON", True)]},

    {"code": "T40-17", "theme": "code", "difficulty": "easy", "qtype": "single", "image_path": "question_17.png",
     "text": "Je peux dépasser ce deux-roues :",
     "explanation": "Les voies sont dégagées, je peux dépasser le deux-roues.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-18", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_18.png",
     "text": "Après cette signalisation, la vitesse est limitée à :",
     "explanation": "Le panneau indique une entrée d'agglomération. La vitesse y est limitée à 50 km/h dans toutes les agglomérations, sauf indication contraire.",
     "choices": [("A", "40 km/h", False), ("B", "50 km/h", True), ("C", "60 km/h", False)]},

    {"code": "T40-19", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_19.png",
     "text": "Cette signalisation annonce un passage à niveau :",
     "explanation": "Le panneau triangulaire annonce un passage à niveau sans barrières ni demi-barrières. Je ralentis et je m'assure qu'aucun train n'arrive.",
     "choices": [("A", "Sans barrières", True), ("B", "Avec barrières", False), ("C", "Avec demi-barrières", False)]},

    {"code": "T40-20", "theme": "regulation", "difficulty": "medium", "qtype": "single", "image_path": None,
     "text": "Le nombre maximum de points retirés pour plusieurs contraventions simultanées est de :",
     "explanation": "Dans le cas où plusieurs infractions entraînant retrait de points sont commises simultanément, les retraits de points se cumulent dans la limite des deux tiers du nombre maximal de points, soit 8 points.",
     "choices": [("A", "6 points", False), ("B", "8 points", True), ("C", "12 points", False)]},

    {"code": "T40-21", "theme": "safety", "difficulty": "medium", "qtype": "multi", "image_path": None,
     "text": "Par temps de brouillard, je peux circuler avec les feux de brouillard :",
     "explanation": "En cas de brouillard, je dois toujours circuler avec les feux de croisement allumés. Les feux de brouillard avant peuvent compléter ou remplacer les feux de croisement. Le ou les feux de brouillard arrière peuvent également être allumés.",
     "choices": [("A", "Avant : OUI", True), ("B", "Avant : NON", False),
                 ("C", "Arrière : OUI", True), ("D", "Arrière : NON", False)]},

    {"code": "T40-22", "theme": "signs", "difficulty": "medium", "qtype": "single", "image_path": "question_22.png",
     "text": "Dans cette situation (entrée d'agglomération « Messy », panneau jaune de route prioritaire) :",
     "explanation": "Le panneau rectangulaire « Messy » indique une entrée d'agglomération : la vitesse y est limitée à 50 km/h à partir de ce panneau dans toute l'agglomération. Le panneau jaune indique le caractère prioritaire de la chaussée sur laquelle je circule. Entrant dans cette agglomération, je ralentis.",
     "choices": [("A", "J'accélère", False), ("B", "Je maintiens ma vitesse", False), ("C", "Je ralentis", True)]},

    {"code": "T40-23", "theme": "priority", "difficulty": "medium", "qtype": "single", "image_path": "question_23.png",
     "text": "Dans cette situation (la voiture bleue a un « STOP ») :",
     "explanation": "Le panneau et le marquage au sol indiquent que la voiture bleue a un « STOP ». Elle doit me céder le passage.",
     "choices": [("A", "Je m'arrête", False), ("B", "Je passe", True)]},

    {"code": "T40-24", "theme": "safety", "difficulty": "medium", "qtype": "single", "image_path": "question_24.png",
     "text": "Je peux dépasser ce camion :",
     "explanation": "Un véhicule est en train de me dépasser, je ne peux pas me déporter sur la file de gauche pour dépasser le camion.",
     "choices": [("A", "OUI", False), ("B", "NON", True)]},

    {"code": "T40-25", "theme": "regulation", "difficulty": "medium", "qtype": "single", "image_path": "question_25.png",
     "text": "La vitesse est limitée à :",
     "explanation": "La vitesse hors agglomération est limitée à 90 km/h, sauf en cas de pluie ou pour les jeunes conducteurs dont la vitesse est limitée à 80 km/h.",
     "choices": [("A", "90 km/h", True), ("B", "100 km/h", False), ("C", "110 km/h", False)]},

    {"code": "T40-26", "theme": "signs", "difficulty": "medium", "qtype": "single", "image_path": "question_26.png",
     "text": "Je circule sur une route prioritaire :",
     "explanation": "Le panneau jaune indique le caractère prioritaire d'une route. Il n'est pas implanté à proximité d'une intersection mais à environ 50 mètres après chaque intersection, le long de la route, en rappel.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-27", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_27.png",
     "text": "Dans cette situation, je m'arrête :",
     "explanation": "Le feu est rouge, il impose l'arrêt absolu.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-28", "theme": "regulation", "difficulty": "easy", "qtype": "single", "image_path": "question_28.png",
     "text": "Après cette signalisation, la vitesse est limitée :",
     "explanation": "La vitesse est limitée à 50 km/h dans toutes les agglomérations, sans qu'il soit nécessaire de l'indiquer par un panneau de limitation de vitesse.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-29", "theme": "priority", "difficulty": "medium", "qtype": "single", "image_path": "question_29.png",
     "text": "La voiture bleue tourne à gauche, je vais tout droit, je passe :",
     "explanation": "La signalisation (le panneau et la ligne blanche) indique que la voiture bleue a rencontré un « STOP ». Elle doit marquer l'arrêt et laisser la priorité aux véhicules venant de droite et de gauche. Je passe avant la voiture bleue.",
     "choices": [("A", "Après la voiture bleue", False), ("B", "Avant la voiture bleue", True)]},

    {"code": "T40-30", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_30.png",
     "text": "À la rencontre de cette signalisation (feux tricolores + panneau « enfants ») :",
     "explanation": "Les 2 panneaux annoncent un danger : feux tricolores et un endroit fréquenté par des enfants, donc je ralentis.",
     "choices": [("A", "Je maintiens ma vitesse", False), ("B", "Je ralentis", True)]},

    {"code": "T40-31", "theme": "regulation", "difficulty": "hard", "qtype": "multi", "image_path": None,
     "text": "Si le taux d'alcoolémie d'un conducteur atteint ou dépasse 0,8 g/l, son permis peut être :",
     "explanation": "La suspension et l'annulation du permis de conduire figurent parmi les sanctions en cas de conduite avec un taux d'alcoolémie supérieur à 0,8 g/l.",
     "choices": [("A", "Suspendu : OUI", True), ("B", "Suspendu : NON", False),
                 ("C", "Annulé : OUI", True), ("D", "Annulé : NON", False)]},

    {"code": "T40-32", "theme": "safety", "difficulty": "easy", "qtype": "single", "image_path": "question_32.png",
     "text": "Pour quitter mon stationnement, je peux allumer mon clignotant :",
     "explanation": "Dans mon rétroviseur, la voie est dégagée, je peux quitter mon stationnement. Pour ce faire, je commence par allumer mon clignotant.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-33", "theme": "safety", "difficulty": "medium", "qtype": "single", "image_path": "question_33.png",
     "text": "Pour stationner, je peux éteindre tous mes feux, si l'éclairage public fonctionne toute la nuit :",
     "explanation": "Pour stationner, la nuit, sur un parking aménagé, je peux éteindre tous mes feux indépendamment de l'éclairage public.",
     "choices": [("A", "OUI", True), ("B", "NON", False)]},

    {"code": "T40-34", "theme": "signs", "difficulty": "medium", "qtype": "single", "image_path": "question_34.png",
     "text": "Sur cette route, je peux rencontrer :",
     "explanation": "Le panneau indique une route pour automobiles ; l'accès en est interdit entre autres aux piétons, aux cyclistes, aux cyclomoteurs et aux voiturettes.",
     "choices": [("A", "Des cyclomoteurs", False), ("B", "Des poids lourds", True), ("C", "Des vélos", False)]},

    {"code": "T40-35", "theme": "signs", "difficulty": "easy", "qtype": "single", "image_path": "question_35.png",
     "text": "Je peux (flèches de direction au sol) :",
     "explanation": "Les flèches m'indiquent l'obligation de tourner à droite.",
     "choices": [("A", "Tourner à gauche", False), ("B", "Continuer tout droit", False), ("C", "Tourner à droite", True)]},

    {"code": "T40-36", "theme": "firstaid", "difficulty": "hard", "qtype": "multi", "image_path": None,
     "text": "En présence d'un accident corporel, il faut :",
     "explanation": "En présence d'un accident corporel, il faut appliquer le P.A.S. : Protéger pour avertir les autres usagers, Alerter les forces de police ou de gendarmerie, Secourir les éventuels blessés. Rédiger un constat amiable n'est pas une priorité face à des blessés.",
     "choices": [("A", "Protéger les lieux", True), ("B", "Alerter les secours", True),
                 ("C", "Rédiger un constat amiable", False), ("D", "Secourir", True)]},

    {"code": "T40-37", "theme": "priority", "difficulty": "medium", "qtype": "single", "image_path": "question_37.png",
     "text": "Dans cette situation (feu vert, intersection) :",
     "explanation": "Le feu vert donne l'autorisation de passer, sauf si l'intersection est encombrée. Dans ce cas, je passe. Le panneau indiquant le caractère prioritaire s'applique quand le feu est éteint ou en jaune clignotant.",
     "choices": [("A", "Je m'arrête", False), ("B", "Je passe", True)]},

    {"code": "T40-38", "theme": "safety", "difficulty": "medium", "qtype": "single", "image_path": "question_38.png",
     "text": "Dans cette situation, après le passage de la voiture grise, je peux dépasser :",
     "explanation": "La ligne pointillée du milieu à traits rapprochés remplace la ligne continue, là où celle-ci serait gênante sur les chaussées étroites. Elle permet de dépasser seulement, si les conditions le permettent, un usager roulant très lentement.",
     "choices": [("A", "OUI", False), ("B", "NON", True)]},

    {"code": "T40-39", "theme": "safety", "difficulty": "medium", "qtype": "multi", "image_path": "question_39.png",
     "text": "Par temps de pluie, hors agglomération :",
     "explanation": "Par temps de pluie, hors agglomération, il faut allumer les feux de croisement. Ils peuvent être remplacés ou complétés par les feux de brouillard avant. Les feux de brouillard arrière sont interdits dans ce cas.",
     "choices": [("A", "Je dois allumer mes feux de croisement : OUI", True), ("B", "Je dois allumer mes feux de croisement : NON", False),
                 ("C", "Je peux allumer mes feux de brouillard avant : OUI", True), ("D", "Je peux allumer mes feux de brouillard avant : NON", False)]},

    {"code": "T40-40", "theme": "signs", "difficulty": "medium", "qtype": "single", "image_path": "question_40.png",
     "text": "Je circule :",
     "explanation": "Les panneaux à fond blanc sont implantés sur une route ; sur autoroute, ils sont à fond bleu. Ici je circule sur une route (nationale) et je me dirige vers des autoroutes.",
     "choices": [("A", "Sur une route", True), ("B", "Sur une autoroute", False)]},
]
