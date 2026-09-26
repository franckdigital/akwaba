"""Contenu des cours « Code de la route » (source : Questionnaire de l'examen du code de la route ED2021, Côte d'Ivoire).

Utilisé par la commande `seed_courses_code_route` pour générer les supports PDF et créer les cours.
Chaque cours : titre, résumé, thème, durée, sections (titre + éléments) et points clés.
Un élément est un paragraphe (str), une liste à puces (list[str]) ou un tableau (dict {"table": [[...], ...], "widths": [...]}).
"""

COURSES = [
    {
        "title": "Le permis de conduire et ses catégories",
        "summary": "Code de la route, permis, catégories A à F et visites médicales.",
        "theme": "regulation", "minutes": 25,
        "sections": [
            ("Définitions", [
                "Le code de la route est un ensemble de textes ou de règles de la circulation qui fixent des obligations et des interdictions aux usagers de la route. Il a été créé pour éviter les accidents de la circulation.",
                "Le permis de conduire est un titre délivré par les autorités compétentes permettant à un individu de conduire un véhicule selon sa catégorie.",
            ]),
            ("Les 6 catégories de permis", [
                {"table": [["Permis", "Véhicules autorisés"],
                           ["A", "Motocyclette ou vélomoteur, avec ou sans side-car, tricycle et quadricycle à moteur."],
                           ["B", "Véhicule transportant, outre le conducteur, 8 places assises au maximum, PTAC de 3 500 kg au maximum. Remorque possible : PTAC de 750 kg au maximum."],
                           ["C", "Véhicule articulé ou ensemble articulé de transport de marchandises, PTAC supérieur à 3 500 kg. Remorque : PTAC de 750 kg au maximum."],
                           ["D", "Véhicule de transport de personnes, plus de 8 places assises (conducteur compris), PTAC supérieur à 3 500 kg."],
                           ["E", "Permis supplémentaire nécessaire si une remorque de plus de 750 kg est attelée à un véhicule tracteur."],
                           ["F", "Personnes handicapées : véhicule de catégorie A ou B aménagé selon l'infirmité (insigne GIC ou GIG)."]],
                 "widths": [50, 400]},
            ]),
            ("Bon à savoir à l'examen", [
                "À la question « Pour quelle catégorie postulez-vous ? », répondez : « Je postule pour les catégories ABCDE ». Ne dites jamais « pour toutes les catégories ».",
            ]),
            ("Visites médicales", [
                "Les catégories A et B sont permanentes : la visite médicale n'a lieu qu'une seule fois. Pour les catégories C et D :",
                {"table": [["Âge du conducteur", "Périodicité"], ["Jusqu'à 45 ans", "Tous les 5 ans"], ["De 45 à 55 ans", "Tous les 3 ans"],
                           ["De 55 à 60 ans", "Tous les 2 ans"], ["Plus de 60 ans", "Chaque année"]], "widths": [220, 230]},
            ]),
        ],
        "key_points": ["6 catégories de permis : A, B, C, D, E et F.", "Permis B : 8 places maximum + conducteur, PTAC de 3 500 kg au maximum, remorque de 750 kg au maximum.",
                       "Permis E : remorque de plus de 750 kg.", "Visite médicale unique pour A et B ; périodique pour C et D."],
    },
    {
        "title": "La route et ses éléments",
        "summary": "Route, agglomération, chaussée, voie, accotement, autoroute et catégories de routes.",
        "theme": "code", "minutes": 30,
        "sections": [
            ("Définitions de base", [
                ["La route : passage aménagé et ouvert à la circulation publique.",
                 "L'agglomération : espace sur lequel sont groupés des immeubles bâtis rapprochés, dont l'entrée et la sortie sont signalées par des panneaux.",
                 "La rase campagne : lieu sans habitations."],
            ]),
            ("Les parties d'une route", [
                ["La chaussée : partie de la route recouverte d'un revêtement spécial et réservée à la circulation des véhicules.",
                 "La voie : subdivision de la chaussée permettant la circulation d'une file de véhicules.",
                 "L'axe central : ligne imaginaire ou matérialisée qui divise la chaussée en deux parties égales.",
                 "L'accotement (rase campagne) : partie située de part et d'autre de la chaussée, aménagée pour les cycles et cyclomoteurs.",
                 "Le trottoir (en ville) : partie bordant la chaussée, réservée aux piétons.",
                 "La bande ou piste cyclable : partie de l'accotement ou de la chaussée réservée aux cycles."],
            ]),
            ("Catégories de routes", [
                ["Routes à grande circulation : assurent la continuité des itinéraires principaux. On les reconnaît à la flèche barrée, au losange à fond jaune et au panneau à trois symboles.",
                 "Routes non classées à grande circulation : aux intersections, on respecte la signalisation ; sans signal de priorité, on cède le passage aux usagers venant de droite.",
                 "Route secondaire : non prioritaire et non classée à grande circulation.",
                 "Voie ou chemin sans issue : rue raccordée à aucune autre rue.",
                 "Voie express ou boulevard : deux chaussées séparées par un terre-plein central ; ressemble à une autoroute sans en être une."],
                "Une route à grande circulation perd sa priorité devant : un agent réglant la circulation vu de face ou de dos, un feu rouge, un panneau stop, l'entrée d'une agglomération, le losange à fond jaune barré, un véhicule sur rail, un véhicule prioritaire annonçant son approche.",
            ]),
            ("L'autoroute", [
                "Voie routière isolée de l'extérieur, conçue pour une circulation plus rapide et plus sûre. Deux sortes : l'autoroute de dégagement (zones urbaines) et l'autoroute de liaison (rase campagne).",
                ["Parties : deux chaussées, un terre-plein central, la voie d'accélération, la voie de décélération, les bretelles d'accès et de sortie, la bande d'arrêt d'urgence, les accotements.",
                 "Circulation à sens unique sur chaque chaussée : après avoir dépassé par la gauche, on reprend sa voie à droite."],
                "Accès interdit aux usagers qui ne peuvent se déplacer qu'à vitesse réduite : piétons, cyclistes, cyclomoteurs, animaux, cavaliers, véhicules à traction non mécanique, transports exceptionnels, véhicules ne pouvant atteindre 40 km/h.",
                "Manœuvres interdites : s'arrêter ou stationner (sauf force majeure), circuler sur les zébras et sur la bande d'arrêt d'urgence, faire marche arrière, traverser la bande centrale séparative.",
            ]),
        ],
        "key_points": ["Chaussée = véhicules ; trottoir = piétons ; accotement = cycles.", "Route à grande circulation : flèche barrée, losange jaune, panneau à trois symboles.",
                       "Autoroute : ni arrêt, ni marche arrière, ni demi-tour."],
    },
    {
        "title": "La signalisation routière",
        "summary": "Panneaux, marquages au sol, feux tricolores et gestes de l'agent.",
        "theme": "signs", "minutes": 45,
        "sections": [
            ("Les 4 sortes de signalisation", [
                ["Signalisation verticale : tous les panneaux implantés le long de la route.",
                 "Signalisation horizontale : marques et marquages peints sur la chaussée.",
                 "Signalisation lumineuse : les feux (vert, jaune, rouge).",
                 "Signalisation gestuelle : gestes d'un agent en tenue réglant la circulation."],
                "Ordre de priorité : l'agent de l'ordre prime sur les feux, les feux priment sur les panneaux.",
            ]),
            ("Reconnaître un panneau : forme, couleur, symbole", [
                {"table": [["Forme", "Couleur", "Annoncé à", "Signifie"],
                           ["Triangle", "Rouge et blanc", "50 m en agglomération, 150 m en dehors", "Danger"],
                           ["Rond", "Rouge et blanc", "À l'endroit", "Ordre, interdiction ou prescription"],
                           ["Rond", "Bleu foncé et blanc", "À l'endroit", "Obligation"],
                           ["Carré", "Bleu foncé et blanc", "À l'endroit ou avant, selon les besoins", "Indication"],
                           ["Rectangle", "Blanc", "À l'endroit", "Localisation"],
                           ["Flèche", "Vert ou bleu", "Là où il faut changer de direction", "Direction"]],
                 "widths": [70, 110, 150, 120]},
                "Face à un panneau de danger (triangle, bordure rouge, fond blanc, symbole noir) : ralentir et adapter sa vitesse au danger.",
                "Les panneaux de prescription absolue sont ronds : interdiction, fin d'interdiction, obligation, fin d'obligation. Les panneaux de simple indication sont carrés ou rectangulaires.",
                "Les panneaux temporaires signalent des travaux ou obstacles provisoires. Un panonceau est un petit panneau placé sous un panneau pour donner des précisions.",
            ]),
            ("Les feux tricolores", [
                {"table": [["Feu", "Comportement"],
                           ["Vert", "J'ai l'autorisation de passer."],
                           ["Jaune fixe", "Arrêt, sauf si je suis trop près et que le freinage est dangereux pour moi ou pour les véhicules qui me suivent."],
                           ["Rouge", "Arrêt obligatoire, interdiction de passer."],
                           ["Flèche jaune clignotante", "Autorise à franchir le feu rouge dans la direction indiquée."],
                           ["Rouge clignotant (feu unique)", "Arrêt obligatoire jusqu'à extinction : passages à niveau, ponts mobiles, bacs, casernes de pompiers."],
                           ["Jaune clignotant (feu unique)", "Prudence, ralentir. Ne modifie pas les règles de priorité."]],
                 "widths": [140, 310]},
                "Quand les feux fonctionnent normalement, on ne tient pas compte du panneau situé sous le feu. Feux éteints ou jaunes clignotants : on respecte le panneau ; sans panneau, priorité à droite.",
            ]),
            ("L'agent réglant la circulation", [
                {"table": [["Position de l'agent", "Signification"], ["Vu de face ou de dos", "Arrêtez-vous."], ["Bras levé", "Arrêtez-vous."],
                           ["Vu de profil", "Passez sans vous arrêter."], ["Bras balancé de haut en bas", "Ralentissez."]], "widths": [200, 250]},
            ]),
            ("La signalisation horizontale", [
                "Marquages : lignes de rive, ligne discontinue, ligne continue, ligne d'avertissement, flèches de rabattement, lignes mixtes ou accolées, ligne d'effet des feux, ligne de cédez le passage, ligne stop, ligne de dissuasion, flèches de sélection, marquages provisoires.",
            ]),
        ],
        "key_points": ["Agent > feux > panneaux.", "Triangle = danger ; rond rouge = interdiction ; rond bleu = obligation ; carré bleu = indication.",
                       "Danger annoncé à 50 m en agglomération, 150 m hors agglomération.", "Feu jaune fixe : arrêt sauf freinage dangereux."],
        "image": "panneaux",
    },
    {
        "title": "Priorités et intersections",
        "summary": "R.A.S.V.O., priorité à droite, priorité de passage, cédez le passage, véhicules prioritaires.",
        "theme": "priority", "minutes": 30,
        "sections": [
            ("Aborder une intersection : R.A.S.V.O.", [
                ["R : Ralentir.", "A : Avertir.", "S : Sélectionner sa voie.", "V : Vérifier si la voie à rencontrer est libre.", "O : Observer l'une des règles de priorité."],
                "Une intersection est un lieu de jonction de deux ou plusieurs routes. Elle peut être avec ou sans signalisation.",
            ]),
            ("Les trois règles de priorité", [
                "La priorité est un privilège qui permet au conducteur d'exécuter une manœuvre avant un autre.",
                {"table": [["Règle", "Définition"],
                           ["Priorité à droite", "Laisser passer d'abord les usagers venant de ma droite, à une intersection de deux routes de même valeur."],
                           ["Priorité de passage", "Passer sans tenir compte des usagers venant de droite comme de gauche (un avantage, sans dispense de précautions)."],
                           ["Cédez le passage", "Laisser passer d'abord les usagers venant de droite comme de gauche (une obligation)."]],
                 "widths": [110, 340]},
            ]),
            ("Quand applique-t-on chaque règle ?", [
                {"table": [["Règle", "Cas"],
                           ["Priorité à droite", "Deux routes secondaires ; intersection sans signalisation ; feu jaune clignotant ; sens giratoire obligatoire ; balise d'intersection."],
                           ["Priorité de passage", "Feu vert ; flèche barrée ; losange à fond jaune ; passage protégé ; passage à niveau barrière levée ; agent vu de profil."],
                           ["Cédez le passage", "Feu rouge ; panneau stop ; agent vu de dos ou de face ; véhicule sur rail ; balise de cédez le passage ; véhicule prioritaire annonçant son approche."]],
                 "widths": [110, 340]},
            ]),
            ("Véhicules prioritaires", [
                ["Véhicules de police, gendarmerie, lutte contre l'incendie, douanes, transport de détenus, SAMU.",
                 "Ils ne sont pas soumis aux limitations de vitesse. Il faut leur céder le passage lorsqu'ils utilisent leurs avertisseurs sonores ou lumineux : ralentir, voire s'arrêter et se ranger."],
                "Ne sont pas prioritaires (véhicules d'intervention urgente) : ambulances, véhicules de gaz et d'électricité secours, transports de fonds, véhicules de médecin de garde.",
            ]),
        ],
        "key_points": ["R.A.S.V.O. : Ralentir, Avertir, Sélectionner, Vérifier, Observer.", "3 règles : priorité à droite, priorité de passage, cédez le passage.",
                       "Cédez le passage devant : feu rouge, stop, agent de face/dos, véhicule prioritaire."],
    },
    {
        "title": "Dépassement, croisement, arrêt et stationnement",
        "summary": "Règles de dépassement, chaussée rétrécie, arrêt, stationnement gênant, dangereux et abusif.",
        "theme": "priority", "minutes": 35,
        "sections": [
            ("Le dépassement", [
                "Le dépassement est le passage de véhicules l'un au-devant de l'autre, allant dans le même sens. Il se fait normalement à gauche. Trois sortes : normal (à gauche), toléré, exceptionnel (à droite).",
                "Précautions à prendre :",
                ["Ne pas être dans un cas d'interdiction.", "Avoir la possibilité de reprendre sa place à droite.", "Avoir une réserve suffisante d'accélération.",
                 "Ne pas gêner les usagers venant en face.", "Regarder dans les rétroviseurs, avertir (clignotant, avertisseur), s'assurer d'être compris.",
                 "Vérifier une nouvelle fois derrière soi, déboîter en accélérant franchement.", "Laisser un intervalle latéral d'au moins un mètre.", "Reprendre sa place à droite après avoir fini de dépasser."],
                "Interdictions de dépasser : signalisation verticale (interdictions, rétrécissement de la chaussée), signalisation horizontale (ligne continue, lignes accolées, lignes d'avertissement, flèches de rabattement), circonstances (risque de gêner un usager venant en sens inverse, qui précède ou qui suit).",
            ]),
            ("Le croisement", [
                "Le croisement est le passage de deux véhicules l'un à côté de l'autre, allant en sens inverse : il faut toujours serrer à droite.",
                ["Passages étroits : le véhicule le plus encombrant laisse le passage au plus petit, sauf signalisation contraire.",
                 "Chaussées en pente : le véhicule qui descend s'arrête le premier ; si une marche arrière est nécessaire, le véhicule le plus maniable l'effectue."],
                "Manœuvres interdites dans une chaussée rétrécie : s'arrêter, dépasser, stationner, faire demi-tour, faire marche arrière.",
            ]),
            ("Arrêt et stationnement", [
                ["Arrêt : immobilisation momentanée (montée ou descente de personnes, chargement ou déchargement).",
                 "Stationnement : immobilisation prolongée sur la chaussée ou l'accotement."],
                {"table": [["Mode", "Description"], ["En épi", "Véhicule garé en biais, une seule roue proche du trottoir."],
                           ["En bataille", "Véhicule perpendiculaire au trottoir."], ["En créneau", "Véhicule parallèle au trottoir."]], "widths": [110, 340]},
                "Modalités : stationnement latéral, unilatéral, à alternance semi-mensuelle, zone bleue.",
            ]),
            ("Stationnement dangereux, gênant, abusif", [
                ["Dangereux (visibilité insuffisante) : intersections, virages, sommet des côtes, passages à niveau, souterrains et tunnels.",
                 "Gênant : trottoirs, passages piétons, pistes cyclables, couloirs d'autobus, emplacements réservés (police, pompiers, ambulances, taxis), arrêts d'autobus, ponts et tunnels, à proximité des signaux lumineux ou panneaux, entre le bord de la chaussée et une ligne continue.",
                 "Abusif : stationnement ininterrompu au même endroit pendant plus de 7 jours (ou durée fixée par la réglementation locale)."],
            ]),
        ],
        "key_points": ["Dépassement normal : à gauche, retour à droite, intervalle d'au moins 1 m.", "Croisement : toujours serrer à droite.", "Stationnement abusif : plus de 7 jours."],
    },
    {
        "title": "Virages, adhérence et freinage",
        "summary": "R.A.S., force centrifuge, adhérence, dérapage, aquaplaning, distance de sécurité et de freinage.",
        "theme": "safety", "minutes": 35,
        "sections": [
            ("Aborder un virage : R.A.S.", [
                ["Ralentir avant le virage, adapter sa vitesse à la difficulté de la courbe, regarder le plus loin possible, garder une réserve de puissance.",
                 "Avertir : le jour, avec le klaxon ; la nuit, avec les feux de route.", "Serrer sur le côté en suivant la courbe du virage."],
                "Dans un virage il est interdit de : s'arrêter, dépasser, stationner, faire demi-tour, faire marche arrière. Il existe deux sortes de virages : à droite et à gauche.",
            ]),
            ("Force centrifuge", [
                "La force centrifuge tend à pousser le véhicule vers l'extérieur du virage. Elle augmente lorsque le virage est serré, lorsque le véhicule est chargé et surtout lorsque la vitesse est élevée.",
            ]),
            ("Adhérence et dérapage", [
                ["L'adhérence : les surfaces du pneu et de la chaussée s'accrochent bien l'une à l'autre. Elle dépend des pneus, de la chaussée et de la suspension.",
                 "Facteurs qui diminuent l'adhérence : pluie, feuilles mortes, boue, gravillons, neige ou verglas.",
                 "Le dérapage : le véhicule glisse latéralement parce que ses roues ont perdu leur adhérence."],
                "Aquaplaning : perte d'adhérence due à une mince pellicule d'eau entre la chaussée et les pneus ; on ne contrôle plus la direction. Pour l'éviter : pneus en bon état et vitesse réduite sur route mouillée.",
            ]),
            ("Freinage et distances", [
                ["Dispositifs de freinage : frein principal (à pied), frein de parcage (à main) et frein moteur.",
                 "Distance de sécurité : intervalle minimum entre mon véhicule et celui qui me précède.",
                 "Distance de freinage : distance parcourue pendant que les freins éliminent l'énergie cinétique ; elle dépend du chargement, de la vitesse et de l'adhérence.",
                 "Temps de réaction : temps écoulé entre la perception d'un signal ou événement et l'action qui suit."],
            ]),
            ("Brouillard et vent", [
                ["Brouillard : réduire sa vitesse, allumer les feux de brouillard avant et arrière, augmenter les distances de sécurité, se guider avec le marquage au sol, éviter de dépasser. Ne jamais utiliser les feux de route.",
                 "Vent violent : être attentif aux écarts des autres usagers (deux-roues), augmenter les intervalles de sécurité aux croisements et dépassements."],
            ]),
        ],
        "key_points": ["R.A.S. : Ralentir, Avertir, Serrer.", "Distance de freinage = chargement + vitesse + adhérence.", "Brouillard : jamais de feux de route."],
    },
    {
        "title": "Accidents, alcool et premiers secours",
        "summary": "Causes d'accidents, conduite à tenir (P.A.S.), délits, alcoolémie et passages à niveau.",
        "theme": "safety", "minutes": 40,
        "sections": [
            ("Les accidents de la circulation", [
                "Un accident est un fait imprévisible et non souhaité qui advient en circulation. Facteurs : humain, matériel, environnemental. Trois sortes : matériel, corporel, mortel.",
                {"table": [["Cause", "Part"], ["Non-respect des grandes règles du code (refus de priorité, circulation à gauche, dépassement irrégulier)", "50 %"],
                           ["Vitesse excessive ou non adaptée", "25 %"], ["Consommation exagérée d'alcool", "12 %"], ["Inattention ou fatigue", "8 %"],
                           ["Facteurs divers (panne, animaux, obstacles non signalés…)", "5 %"]], "widths": [370, 80]},
            ]),
            ("En cas d'accident", [
                "Si vous êtes impliqué, même dans un accident minime : vous arrêter et donner votre identité aux personnes concernées. Sinon : délit de fuite (amende et emprisonnement).",
                "Si vous êtes témoin : vous arrêter et porter secours, en adoptant le P.A.S. (sinon, poursuite possible pour non-assistance à personne en danger).",
                ["P — Protéger : baliser les lieux (triangles de présignalisation dans chaque sens, feux de détresse) ; la nuit, éclairer les véhicules accidentés.",
                 "A — Alerter : composer le 180 ; préciser la nature de l'accident, le nombre et l'état des blessés, les véhicules impliqués, l'emplacement exact, les circonstances particulières.",
                 "S — Secourir : s'occuper des blessés sans aggraver leur état."],
                "À ne pas faire : donner à boire (même de l'eau) ; déplacer un blessé ou le sortir du véhicule sauf danger immédiat (incendie, explosion, noyade) ; ôter le casque d'un motard ; transporter un blessé dans une voiture.",
                "À faire : réconforter le blessé par des paroles rassurantes, le couvrir, desserrer ses vêtements.",
            ]),
            ("Délits et alcool", [
                ["Délits : délit de fuite, homicide ou blessure par imprudence, conduite en état d'ivresse.",
                 "Alcoolémie : quantité d'alcool contenue dans le sang. En Côte d'Ivoire, le taux admis est de 0,8 gramme par litre de sang ; au-delà, c'est un délit.",
                 "L'alcootest décèle la présence d'alcool dans l'air expiré ; l'éthylomètre mesure avec précision la teneur en alcool."],
            ]),
            ("Les passages à niveau", [
                "Un passage à niveau est un lieu de jonction d'une chaussée à une voie ferrée. Trois types : avec barrière à fonctionnement manuel, avec demi-barrière à fonctionnement automatique, sans barrière.",
            ]),
        ],
        "key_points": ["P.A.S. : Protéger, Alerter (180), Secourir.", "Taux d'alcool maximum : 0,8 g/l de sang.", "Ne jamais donner à boire ni ôter le casque d'un motard.",
                       "Délit de fuite : s'arrêter et donner son identité."],
    },
    {
        "title": "Feux, éclairage et mécanique du véhicule",
        "summary": "Feux de croisement et de route, PTAC, angle mort, quatre temps du moteur, V.I.F. et sécurités.",
        "theme": "mechanics", "minutes": 30,
        "sections": [
            ("Les feux d'un véhicule de catégorie B", [
                ["À l'avant : deux feux de route, deux feux de croisement, deux feux de position, deux clignotants, feux de brouillard (facultatifs).",
                 "À l'arrière : deux feux rouges non éblouissants, deux feux stop et un troisième feu stop, deux catadioptres, éclairage de la plaque d'immatriculation, un ou deux feux de recul (lumière blanche)."],
            ]),
            ("Utiliser les feux", [
                {"table": [["Feux", "Quand les allumer"],
                           ["Croisement", "Circulation sur route éclairée en continu ; avant de croiser un véhicule ; en suivant un véhicule de près (sauf en le dépassant) ; visibilité réduite (brouillard, pluie, neige)."],
                           ["Route", "Route non éclairée ou insuffisamment éclairée, sans gêner les autres usagers ; pendant un dépassement, sans éblouir personne."]],
                 "widths": [90, 360]},
            ]),
            ("Notions techniques", [
                ["PTAC (poids total autorisé en charge) : poids maximal officiellement admis à pleine charge, fixé par le service des mines ; indiqué sur la carte grise et la plaque du constructeur.",
                 "Angle mort : endroit inaccessible au champ de vision du conducteur depuis les différents rétroviseurs.",
                 "Les quatre temps du moteur : admission, compression, explosion, échappement."],
            ]),
            ("Le démarrage : être V.I.F.", [
                ["V : Vitesse à passer.", "I : Indicateur de changement de direction.", "F : Frein à main à desserrer."],
            ]),
            ("Les trois sécurités", [
                ["Sécurité active : tout ce qui concourt à la tenue de route, au bon freinage et au bon éclairage (freins, pneumatiques, rotules, roulements, amortisseurs, rétroviseurs).",
                 "Sécurité passive : aménagement du véhicule et installation des passagers ou bagages, de nature à rendre moins graves les conséquences d'un accident.",
                 "Sécurité tertiaire : ensemble des premiers soins reçus par un blessé avant les soins des centres médicaux."],
            ]),
        ],
        "key_points": ["Feux de croisement pour ne pas éblouir ; feux de route sur route non éclairée.", "V.I.F. : Vitesse, Indicateur, Frein à main.",
                       "4 temps du moteur : admission, compression, explosion, échappement."],
    },
    {
        "title": "Vitesses maximales autorisées",
        "summary": "Limites de vitesse selon le type de véhicule : agglomération, route et autoroute.",
        "theme": "regulation", "minutes": 10,
        "sections": [
            ("Tableau des vitesses maximales", [
                {"table": [["Véhicule", "Agglomération", "Routes inter", "Autoroutes"], ["Véhicules légers", "60 km/h", "110 km/h", "120 km/h"],
                           ["Autocars", "50 km/h", "90 km/h", "90 km/h"], ["Camion PTAC < 16 t", "50 km/h", "80 km/h", "80 km/h"],
                           ["Camion PTAC > 16 t", "50 km/h", "70 km/h", "70 km/h"]], "widths": [140, 100, 100, 100]},
                "Les véhicules prioritaires (police, gendarmerie, pompiers, douanes, SAMU) ne sont pas soumis aux limitations de vitesse. La vitesse doit toujours être adaptée à l'état de la route et aux conditions de circulation.",
            ]),
        ],
        "key_points": ["Véhicule léger : 60 (ville), 110 (route), 120 (autoroute).", "Autocar : 50 / 90 / 90.", "Camions : 50 en ville ; 80 (< 16 t) ou 70 (> 16 t) ailleurs."],
    },
]
