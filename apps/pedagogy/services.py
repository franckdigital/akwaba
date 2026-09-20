"""Moteur QCM : tirage, correction immédiate, score, historique, progression, import Excel."""
import random
from datetime import timedelta
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.notify import notify

from .models import THEMES, Attempt, AttemptAnswer, Choice, ImportJob, Question, Quiz


# --------------------------------------------------------------------------- tirage
def question_pool(quiz, school):
    qs = Question.objects.filter(is_active=True, category=quiz.category).filter(Q(school=school) | Q(school__isnull=True))
    if quiz.themes:
        qs = qs.filter(theme__in=quiz.themes)
    if quiz.difficulties:
        qs = qs.filter(difficulty__in=quiz.difficulties)
    return qs


def pick_questions(quiz, school):
    if quiz.mode == Quiz.MANUAL:
        picked = list(quiz.questions.filter(is_active=True).order_by("id"))
    else:
        pool = list(question_pool(quiz, school))
        picked = random.sample(pool, min(quiz.num_questions, len(pool)))
    if quiz.shuffle:
        random.shuffle(picked)
    return picked


# --------------------------------------------------------------------------- tentative
def _expired(attempt):
    limit = attempt.quiz.duration_minutes
    return bool(limit) and timezone.now() > attempt.started_at + timedelta(minutes=limit, seconds=5)


def exam_eligibility(learner):
    """Accès aux examens blancs : score moyen sur l'ensemble des QCM d'entraînement terminés >= seuil de l'auto-école."""
    done = Attempt.objects.filter(learner=learner, is_exam=False, status__in=[Attempt.FINISHED, Attempt.EXPIRED])
    n = done.count()
    average = round(sum(float(a.percent) for a in done) / n, 1) if n else 0.0
    required = getattr(learner.school, "exam_min_average", 60)
    return {"eligible": n > 0 and average >= required, "average": average, "required": required, "quizzes_done": n,
            "missing": max(0, round(required - average, 1)) if n else required}


def start_attempt(quiz, learner):
    if not quiz.is_published:
        raise ValidationError({"detail": "Questionnaire non publié."})
    if quiz.school_id and quiz.school_id != learner.school_id:
        raise PermissionDenied("Questionnaire indisponible pour votre auto-école.")
    from apps.subscriptions.services import require_access
    require_access(learner, "exams" if quiz.is_exam else "quizzes")
    if quiz.category != learner.category and quiz.is_exam:
        raise ValidationError({"detail": "Cet examen ne concerne pas votre catégorie de permis."})

    current = Attempt.objects.filter(quiz=quiz, learner=learner, status=Attempt.IN_PROGRESS).first()
    if quiz.is_exam and not current:
        e = exam_eligibility(learner)
        if not e["eligible"]:
            raise PermissionDenied(
                f"Examens blancs verrouillés : votre score moyen aux QCM est de {e['average']} % sur {e['quizzes_done']} QCM "
                f"terminé(s) ; {e['required']} % sont requis. Entraînez-vous encore !")
    if current:
        if _expired(current):
            finish_attempt(current, expired=True)
        else:
            return current
    used = Attempt.objects.filter(quiz=quiz, learner=learner).count()
    if quiz.max_attempts and used >= quiz.max_attempts:
        raise ValidationError({"detail": f"Nombre maximal de tentatives atteint ({quiz.max_attempts})."})
    if quiz.is_exam and Attempt.objects.filter(quiz=quiz, learner=learner, passed=True).exists():
        raise ValidationError({"detail": "Examen déjà réussi."})

    questions = pick_questions(quiz, learner.school)
    if not questions:
        raise ValidationError({"detail": "Aucune question disponible pour ce questionnaire."})
    with transaction.atomic():
        attempt = Attempt.objects.create(
            quiz=quiz, learner=learner, school=learner.school, number=used + 1, is_exam=quiz.is_exam,
            threshold=quiz.pass_threshold, total_questions=len(questions),
            max_score=quiz.points_per_question * len(questions))
        AttemptAnswer.objects.bulk_create([AttemptAnswer(attempt=attempt, question=q, position=i)
                                           for i, q in enumerate(questions, 1)])
    return attempt


def _labels(question, ids):
    by_id = {c.id: c for c in question.choices.all()}
    return [by_id[i].label for i in sorted(ids, key=lambda i: by_id[i].order if i in by_id else 0) if i in by_id]


def correction_payload(ans):
    q = ans.question
    correct = q.correct_ids()
    choices = list(q.choices.all())
    texts = {c.id: c.text for c in choices}
    return {
        "question": q.id,
        "is_correct": ans.is_correct,
        "verdict": "Bonne réponse" if ans.is_correct else "Réponse incorrecte",
        "your_answer": _labels(q, ans.selected),
        "your_answer_text": [texts.get(i, "") for i in ans.selected],
        "correct_answer": _labels(q, correct),
        "correct_answer_text": [c.text for c in choices if c.id in correct],
        "explanation": q.explanation,
        "points": ans.points,
    }


def answer_question(attempt, question_id, selected):
    if attempt.status != Attempt.IN_PROGRESS:
        raise ValidationError({"detail": "Tentative terminée."})
    if _expired(attempt):
        finish_attempt(attempt, expired=True)
        raise ValidationError({"detail": "Temps écoulé : la tentative a été clôturée."})
    ans = (attempt.answers.select_related("question").filter(question_id=question_id).first())
    if ans is None:
        raise ValidationError({"question": "Question absente de cette tentative."})
    if ans.answered:
        raise ValidationError({"detail": "Question déjà validée."})
    q = ans.question
    valid_ids = {c.id for c in q.choices.all()}
    try:
        selected = {int(x) for x in selected}
    except (TypeError, ValueError):
        raise ValidationError({"choices": "Identifiants invalides."})
    if not selected or not selected <= valid_ids:
        raise ValidationError({"choices": "Sélectionnez au moins une réponse valide."})
    if q.qtype != Question.MULTI and len(selected) != 1:
        raise ValidationError({"choices": "Une seule réponse attendue."})
    ok = selected == q.correct_ids()
    ans.selected = sorted(selected)
    ans.answered = True
    ans.is_correct = ok
    ans.points = attempt.quiz.points_per_question if ok else Decimal(0)
    ans.answered_at = timezone.now()
    ans.save()
    return ans


@transaction.atomic
def finish_attempt(attempt, expired=False):
    attempt = Attempt.objects.select_for_update().select_related("quiz", "learner", "learner__school").get(pk=attempt.pk)
    if attempt.status != Attempt.IN_PROGRESS:
        return attempt
    answers = list(attempt.answers.all())
    correct = sum(1 for a in answers if a.is_correct)
    attempt.total_questions = len(answers)
    attempt.correct_count = correct
    attempt.wrong_count = len(answers) - correct
    attempt.score = sum((a.points for a in answers), Decimal(0))
    attempt.max_score = attempt.quiz.points_per_question * len(answers)
    attempt.percent = (attempt.score * 100 / attempt.max_score).quantize(Decimal("0.01")) if attempt.max_score else Decimal(0)
    # comparaison exacte (sans arrondi) : 35/50 = 70 % => admis ; 34/50 = 68 % => non admis
    attempt.passed = bool(attempt.max_score) and attempt.score * 100 >= attempt.threshold * attempt.max_score
    attempt.status = Attempt.EXPIRED if expired else Attempt.FINISHED
    attempt.finished_at = timezone.now()
    attempt.duration_seconds = int((attempt.finished_at - attempt.started_at).total_seconds())
    attempt.save()
    if attempt.is_exam:
        _after_exam(attempt)
    else:
        notify(attempt.learner.user, "result", f"Résultat : {attempt.quiz.title}",
               f"Score {attempt.correct_count}/{attempt.total_questions} ({attempt.percent} %).")
    return attempt


def _after_exam(attempt):
    from apps.exams.services import issue_certificate
    learner = attempt.learner
    label = "ADMIS" if attempt.passed else "NON ADMIS"
    notify(learner.user, "exam_result", f"Résultat de l'examen : {label}",
           f"{attempt.correct_count}/{attempt.total_questions} - {attempt.percent} %.", channels=("inapp", "email", "sms"))
    if attempt.passed:
        learner.status = "passed"
        learner.save(update_fields=["status", "updated_at"])
        issue_certificate(attempt)
    else:
        q = attempt.quiz
        if q.max_attempts and Attempt.objects.filter(quiz=q, learner=learner).count() >= q.max_attempts:
            learner.status = "failed"
            learner.save(update_fields=["status", "updated_at"])


def attempt_summary(attempt):
    return {
        "id": attempt.id, "quiz": attempt.quiz_id, "quiz_title": attempt.quiz.title, "number": attempt.number,
        "status": attempt.status, "result": attempt.result_label, "score": attempt.score, "max_score": attempt.max_score,
        "score_label": f"{attempt.correct_count}/{attempt.total_questions}", "percent": attempt.percent,
        "correct_count": attempt.correct_count, "wrong_count": attempt.wrong_count,
        "total_questions": attempt.total_questions, "passed": attempt.passed, "threshold": attempt.threshold,
        "duration_seconds": attempt.duration_seconds, "started_at": attempt.started_at, "finished_at": attempt.finished_at,
        "is_exam": attempt.is_exam,
    }


def attempt_review(attempt):
    """Récapitulatif question par question (choix apprenant / bonne réponse / résultat)."""
    show = attempt.quiz.show_corrections
    rows = []
    for a in attempt.answers.select_related("question").prefetch_related("question__choices"):
        row = {"position": a.position, "question": a.question_id, "text": a.question.text, "answered": a.answered,
               "result": "correct" if a.is_correct else "incorrect", "is_correct": a.is_correct}
        if show:
            row.update(correction_payload(a))
        else:
            row["your_answer"] = _labels(a.question, a.selected)
        rows.append(row)
    return rows


def attempt_questions(attempt):
    """Questions à présenter (sans jamais révéler la bonne réponse)."""
    out = []
    for a in attempt.answers.select_related("question").prefetch_related("question__choices"):
        q = a.question
        item = {"id": q.id, "position": a.position, "text": q.text, "type": q.qtype, "theme": q.theme,
                "image": q.image.url if q.image else None, "answered": a.answered,
                "choices": [{"id": c.id, "label": c.label, "text": c.text} for c in q.choices.all()]}
        if a.answered and attempt.quiz.show_corrections:
            item["correction"] = correction_payload(a)
        out.append(item)
    return out


# --------------------------------------------------------------------------- progression
def learner_progress(learner):
    finished = Attempt.objects.filter(learner=learner, status__in=[Attempt.FINISHED, Attempt.EXPIRED]).select_related("quiz")
    n = finished.count()
    answers = AttemptAnswer.objects.filter(attempt__in=finished, answered=True).select_related("question")
    themes = defaultdict(lambda: [0, 0])
    for a in answers:
        themes[a.question.theme][0] += 1
        themes[a.question.theme][1] += 1 if a.is_correct else 0
    labels = dict(THEMES)
    threshold = learner.school.pass_threshold
    theme_rows = [{"theme": t, "label": labels.get(t, t), "answered": v[0], "correct": v[1],
                   "percent": round(v[1] * 100 / v[0], 1)} for t, v in themes.items() if v[0]]
    mastered = [r for r in theme_rows if r["percent"] >= threshold]
    improve = [r for r in theme_rows if r["percent"] < threshold]
    avg = round(sum(float(a.percent) for a in finished) / n, 1) if n else 0
    available = Quiz.objects.filter(is_published=True, category=learner.category).filter(
        Q(school=learner.school) | Q(school__isnull=True)).count()
    done = finished.values("quiz").distinct().count()
    passed = finished.filter(passed=True).count()
    return {
        "progress_percent": round(min(done, available) * 100 / available, 1) if available else 0,
        "quizzes_done": n, "distinct_quizzes": done, "quizzes_available": available,
        "average_percent": avg,
        "best_scores": [{"quiz": a.quiz.title, "percent": a.percent, "date": a.finished_at}
                        for a in finished.order_by("-percent")[:5]],
        "mastered_themes": mastered, "themes_to_improve": improve, "themes": theme_rows,
        "time_spent_seconds": sum(a.duration_seconds for a in finished),
        "success_rate": round(passed * 100 / n, 1) if n else 0,
        "exam_eligibility": exam_eligibility(learner),
        "history": [attempt_summary(a) for a in finished.order_by("-started_at")[:20]],
    }


# --------------------------------------------------------------------------- import Excel
COLUMNS = ["Code", "Permis", "Thème", "Type", "Question", "A", "B", "C", "D", "Bonne réponse", "Explication"]
OPTIONAL_COLUMNS = ["Sous-thème", "Difficulté", "Image"]
OPTION_LETTERS = ["A", "B", "C", "D", "E", "F"]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


THEME_MAP = {}
for key, label in THEMES:
    THEME_MAP[_norm(key)] = key
    THEME_MAP[_norm(label)] = key
TYPE_MAP = {"vrai faux": "tf", "vf": "tf", "tf": "tf", "boolean": "tf", "type 1": "tf", "1": "tf",
            "unique": "single", "reponse unique": "single", "single": "single", "qcu": "single", "type 2": "single", "2": "single",
            "multiple": "multi", "choix multiple": "multi", "multi": "multi", "qcm": "multi", "type 3": "multi", "3": "multi"}
DIFF_MAP = {"facile": "easy", "easy": "easy", "moyen": "medium", "medium": "medium", "difficile": "hard", "hard": "hard"}
CATS = {"A", "A1", "B", "C", "D", "E", "OTHER"}
HEADER_ALIASES = {"code": "code", "permis": "category", "categorie": "category", "theme": "theme", "type": "type",
                  "question": "text", "enonce": "text", "bonne reponse": "answer", "reponse": "answer",
                  "reponses correctes": "answer", "explication": "explanation", "correction": "explanation",
                  "image": "image", "illustration": "image", "sous theme": "subtheme", "difficulte": "difficulty", "niveau": "difficulty"}
for L in OPTION_LETTERS:
    HEADER_ALIASES[_norm(L)] = L


EXAMPLES = [
    ["Q-0001", "B", "Signalisation", "Réponse unique", "Que signifie un panneau triangulaire à bordure rouge ?",
     "Interdiction", "Danger", "Obligation", "Indication", "B", "Les panneaux triangulaires à bordure rouge signalent un danger.", "Panneaux de danger", "Facile", ""],
    ["Q-0002", "B", "Priorités", "Vrai/Faux", "À une intersection sans signalisation, la priorité est à droite.",
     "", "", "", "", "Vrai", "C'est la règle de la priorité à droite.", "Intersections", "Moyen", ""],
    ["Q-0003", "B", "Sécurité routière", "Choix multiple", "Quels équipements sont obligatoires dans le véhicule ?",
     "Triangle de présignalisation", "Autoradio", "Gilet de sécurité", "Décoration au rétroviseur", "A,C", "Le triangle et le gilet sont obligatoires.", "Équipements", "Moyen", ""],
    ["Q-0004", "B", "Réglementation", "Vrai/Faux", "Le téléphone tenu à la main est autorisé en conduisant.",
     "", "", "", "", "Faux", "Son usage en main est interdit.", "", "Facile", ""],
    ["Q-0005", "B", "Mécanique", "Réponse unique", "Quelle est la profondeur minimale légale des sculptures d'un pneu ?",
     "0,5 mm", "1,6 mm", "3 mm", "5 mm", "B", "1,6 mm est le minimum légal.", "Pneumatiques", "Difficile", ""],
    ["Q-0006", "A", "Comportement du conducteur", "Choix multiple", "Quels facteurs augmentent le risque d'accident ?",
     "Fatigue", "Vitesse excessive", "Respect des distances", "Somnolence", "A,B,D", "Fatigue, vitesse et somnolence sont des facteurs majeurs.", "", "Moyen", ""],
]

INSTRUCTIONS = [
    # colonne, obligatoire, description, valeurs acceptées, exemple
    ("Code", "Oui", "Identifiant unique de la question dans votre banque. Sert à retrouver et mettre à jour une question.", "Texte libre, sans doublon", "Q-0001"),
    ("Permis", "Oui", "Catégorie de permis concernée.", "A, A1, B, C, D, E (liste déroulante)", "B"),
    ("Thème", "Non (défaut : Autre)", "Thème pédagogique de la question.", "Voir l'onglet « Valeurs autorisées »", "Signalisation"),
    ("Type", "Oui", "Format de la question.", "Vrai/Faux · Réponse unique · Choix multiple", "Réponse unique"),
    ("Question", "Oui", "Énoncé complet de la question.", "Texte libre", "Que signifie un feu rouge fixe ?"),
    ("A, B, C, D", "Oui sauf Vrai/Faux", "Propositions de réponse. Au moins 2 pour Réponse unique / Choix multiple. À laisser vides pour Vrai/Faux.", "Texte libre", "S'arrêter"),
    ("Bonne réponse", "Oui", "Lettre(s) de la ou des bonnes propositions. Vrai/Faux : écrire Vrai ou Faux.", "A · B · A,C · A,B,D · Vrai · Faux", "A,C"),
    ("Explication", "Non", "Texte affiché à l'apprenant à la correction, que sa réponse soit juste ou fausse.", "Texte libre", "Le feu rouge impose l'arrêt."),
    ("Sous-thème", "Non", "Précision du thème (pour vos recherches).", "Texte libre", "Panneaux de danger"),
    ("Difficulté", "Non (défaut : Moyen)", "Niveau de difficulté.", "Facile · Moyen · Difficile", "Moyen"),
    ("Image", "Non", "Illustration de la question (panneau, situation…). Deux façons : 1) INSÉRER l'image dans la cellule de la ligne (Insertion > Images) ; 2) écrire ici le NOM du fichier (ex. panneau_stop.png) et le joindre à l'import avec le champ « Images » (fichiers ou .zip).", "png, jpg, webp — 5 Mo max", "panneau_stop.png"),
]

RULES = [
    "La première ligne de l'onglet « QCM » contient les en-têtes : ne les renommez pas et ne les déplacez pas (l'ordre des colonnes peut changer).",
    "Une ligne = une question. Les lignes vides sont ignorées.",
    "Réponse unique : exactement UNE bonne réponse (ex. B). Choix multiple : une ou plusieurs (ex. A,C). Vrai/Faux : Vrai ou Faux.",
    "La bonne réponse doit correspondre à une proposition renseignée (répondre D alors que D est vide est une erreur).",
    "Chaque code doit être unique. Un code déjà présent est signalé comme doublon, sauf si vous cochez « Mettre à jour les questions existantes ».",
    "Une question dont l'énoncé est identique à une question existante du même permis est signalée comme doublon.",
    "Le fichier est d'abord ANALYSÉ : rien n'est enregistré avant votre confirmation. Les lignes en erreur peuvent être exportées, corrigées puis ré-importées.",
    "Images : soit insérées directement dans la cellule (elles suivent la ligne), soit référencées par leur nom de fichier dans la colonne « Image » et jointes à l'import (plusieurs fichiers ou un .zip). Une image manquante ou invalide rend la ligne en erreur.",
    "Supprimez les lignes d'exemple (Q-0001 à Q-0006) avant d'importer vos propres questions, ou utilisez le modèle vide.",
]


def build_template(blank=False):
    """Modèle Excel d'import : onglet QCM (exemples ou vide) + mode d'emploi + valeurs autorisées."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "QCM"
    headers = COLUMNS + OPTIONAL_COLUMNS
    ws.append(headers)
    required = {"Code", "Permis", "Type", "Question", "Bonne réponse"}
    red = PatternFill("solid", fgColor="E02027")
    grey = PatternFill("solid", fgColor="2B2B2B")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = red if c.value in required or c.value in ("A", "B", "C", "D") else grey
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.row_dimensions[1].height = 26
    if not blank:
        for row in EXAMPLES:
            ws.append(row)
    widths = [10, 8, 24, 16, 52, 24, 24, 24, 24, 14, 44, 20, 12, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    for row in ws.iter_rows(min_row=2, max_row=max(ws.max_row, 2)):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"

    # Onglet valeurs (sert aussi aux listes déroulantes)
    vs = wb.create_sheet("Valeurs autorisées")
    vs.append(["Permis", "Thème", "Type", "Difficulté", "Bonne réponse (exemples)"])
    cats = ["A", "A1", "B", "C", "D", "E"]
    themes = [label for _, label in THEMES]
    types = ["Vrai/Faux", "Réponse unique", "Choix multiple"]
    diffs = ["Facile", "Moyen", "Difficile"]
    answers = ["A", "B", "C", "D", "A,C", "A,B,D", "Vrai", "Faux"]
    for i in range(max(len(cats), len(themes), len(types), len(diffs), len(answers))):
        vs.append([x[i] if i < len(x) else None for x in (cats, themes, types, diffs, answers)])
    for c in vs[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = grey
    for col, w in zip("ABCDE", (10, 30, 20, 14, 26)):
        vs.column_dimensions[col].width = w

    def dv(col, n):
        v = DataValidation(type="list", formula1=f"='Valeurs autorisées'!${col}$2:${col}${n + 1}", allow_blank=True)
        v.error = "Valeur non reconnue : choisissez dans la liste."
        v.showErrorMessage = True
        v.errorStyle = "warning"
        ws.add_data_validation(v)
        return v
    dv("A", len(cats)).add("B2:B2000")
    dv("B", len(themes)).add("C2:C2000")
    dv("C", len(types)).add("D2:D2000")
    dv("D", len(diffs)).add("M2:M2000")

    ins = wb.create_sheet("Mode d'emploi")
    ins.append(["MODÈLE D'IMPORT DES QUESTIONS QCM — MODE D'EMPLOI"])
    ins["A1"].font = Font(bold=True, size=14, color="E02027")
    ins.append([])
    ins.append(["Colonne", "Obligatoire", "Description", "Valeurs acceptées", "Exemple"])
    for c in ins[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = red
    for row in INSTRUCTIONS:
        ins.append(list(row))
    ins.append([])
    ins.append(["RÈGLES À RESPECTER"])
    ins.cell(row=ins.max_row, column=1).font = Font(bold=True, color="E02027")
    for i, r in enumerate(RULES, start=1):
        ins.append([f"{i}.", r])
    for col, w in zip("ABCDE", (16, 20, 70, 44, 32)):
        ins.column_dimensions[col].width = w
    for row in ins.iter_rows(min_row=3):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    return wb


def _read_rows(fileobj):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(fileobj, data_only=True)
    except Exception:
        raise ValidationError({"file": "Fichier Excel (.xlsx) illisible."})
    ws = wb["QCM"] if "QCM" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValidationError({"file": "Fichier vide."})
    header = [HEADER_ALIASES.get(_norm(h)) for h in rows[0]]
    required = {"code", "category", "type", "text", "answer"}
    missing = required - set(header)
    if missing:
        raise ValidationError({"file": "Colonnes manquantes : " + ", ".join(sorted(missing))
                               + ". Colonnes attendues : " + ", ".join(COLUMNS)})
    # images insérées dans les cellules : rattachées à la ligne d'ancrage
    embedded = {}
    for img in getattr(ws, "_images", []):
        try:
            row = img.anchor._from.row + 1
            data = img._data()
            fmt = (getattr(img, "format", None) or "png").lower()
            embedded.setdefault(row, (data, "jpg" if fmt == "jpeg" else fmt))
        except Exception:
            continue
    return rows[0], header, rows[1:], embedded


MAX_IMAGE = 5 * 1024 * 1024


def collect_images(files):
    """Fichiers joints à l'import (images ou .zip) -> {nom en minuscules: (octets, nom)}."""
    import zipfile
    out = {}
    for f in files or []:
        name = getattr(f, "name", "") or ""
        if name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(f) as z:
                    for info in z.infolist():
                        base = info.filename.rsplit("/", 1)[-1]
                        if info.is_dir() or not base or base.startswith(".") or info.file_size > MAX_IMAGE:
                            continue
                        out[base.lower()] = (z.read(info), base)
            except zipfile.BadZipFile:
                raise ValidationError({"images": f"Archive « {name} » illisible."})
        else:
            out[name.rsplit("/", 1)[-1].lower()] = (f.read(), name)
    return out


def _valid_image(data):
    """-> message d'erreur ou None."""
    if len(data) > MAX_IMAGE:
        return "Image trop lourde (5 Mo max)."
    try:
        import io
        from PIL import Image
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        return "Fichier image invalide."
    return None


def _parse_answer(raw, qtype, options):
    """-> (set de labels corrects, erreur)"""
    raw = str(raw or "").strip()
    if not raw:
        return set(), "Bonne réponse manquante."
    if qtype == "tf":
        v = _norm(raw)
        if v in ("vrai", "v", "true", "oui", "a"):
            return {"Vrai"}, None
        if v in ("faux", "f", "false", "non", "b"):
            return {"Faux"}, None
        return set(), "Bonne réponse Vrai/Faux invalide."
    letters = [x for x in re.split(r"[,;/\s+&]+", raw.upper()) if x]
    if len(letters) == 1 and len(letters[0]) > 1 and set(letters[0]) <= set(OPTION_LETTERS):
        letters = list(letters[0])
    bad = [x for x in letters if x not in options]
    if bad:
        return set(), f"Bonne réponse '{', '.join(bad)}' ne correspond à aucune proposition renseignée."
    return set(letters), None


def analyse_workbook(fileobj, school, update_existing=False, images=None):
    """Analyse sans écrire en base. -> (valid_items, errors, total)"""
    raw_header, header, data_rows, embedded = _read_rows(fileobj)
    images = images or {}
    existing_codes = dict(Question.objects.filter(school=school).values_list("code", "id"))
    # codes de la banque centrale Akwaba : jamais modifiables par une auto-école, mais réutilisables dans ses questionnaires
    central_codes = dict(Question.objects.filter(school__isnull=True).values_list("code", "id")) if school is not None else {}
    existing_texts = {(c, _norm(t)) for c, t in Question.objects.filter(
        Q(school=school) | Q(school__isnull=True)).values_list("category", "text")}
    seen_codes, seen_texts = set(), set()
    valid, errors, total = [], [], 0
    for idx, row in enumerate(data_rows, start=2):
        if row is None or all(v in (None, "") for v in row):
            continue
        total += 1
        rec = {}
        for h, v in zip(header, row):
            if h:
                rec[h] = "" if v is None else str(v).strip()
        problems = []
        code = rec.get("code", "")
        if not code:
            problems.append("Code manquant.")
        category = rec.get("category", "").upper()
        if category not in CATS:
            problems.append(f"Permis invalide '{rec.get('category', '')}'.")
        theme = THEME_MAP.get(_norm(rec.get("theme", "")), None) if rec.get("theme") else "other"
        if theme is None:
            problems.append(f"Thème inconnu '{rec.get('theme')}'.")
        qtype = TYPE_MAP.get(_norm(rec.get("type", "")))
        if qtype is None:
            problems.append(f"Type invalide '{rec.get('type', '')}'.")
        text = rec.get("text", "")
        if not text:
            problems.append("Énoncé manquant.")
        difficulty = "medium"
        if rec.get("difficulty"):
            difficulty = DIFF_MAP.get(_norm(rec["difficulty"]))
            if difficulty is None:
                problems.append(f"Difficulté invalide '{rec['difficulty']}'.")
        options = {L: rec[L] for L in OPTION_LETTERS if rec.get(L)}
        if qtype == "tf":
            options = {"Vrai": "Vrai", "Faux": "Faux"}
        elif qtype in ("single", "multi") and len(options) < 2:
            problems.append("Au moins deux propositions sont requises.")
        correct, err = (set(), None)
        if qtype:
            correct, err = _parse_answer(rec.get("answer"), qtype, options)
            if err:
                problems.append(err)
            elif qtype in ("single", "tf") and len(correct) != 1:
                problems.append("Une seule bonne réponse attendue pour ce type.")
        image = None
        ref = rec.get("image", "")
        if ref:
            found = images.get(ref.rsplit("/", 1)[-1].lower())
            if found is None:
                problems.append(f"Image « {ref} » introuvable parmi les fichiers joints.")
            else:
                image = found
        elif idx in embedded:
            data, ext = embedded[idx]
            image = (data, f"{code or 'question'}.{ext}")
        if image is not None:
            err_img = _valid_image(image[0])
            if err_img:
                problems.append(err_img)
                image = None
        duplicate = False
        existing_id = existing_codes.get(code)
        if code and code in seen_codes:
            problems.append(f"Doublon : le code '{code}' apparaît plusieurs fois dans le fichier.")
            duplicate = True
        elif code and existing_id and not update_existing:
            problems.append(f"Doublon : le code '{code}' existe déjà.")
            duplicate = True
        elif code and not existing_id and code in central_codes:
            problems.append(f"Doublon : le code '{code}' existe dans la banque centrale Akwaba.")
            duplicate = True
            existing_id = central_codes[code]
        key = (category, _norm(text))
        if text and not duplicate and not existing_id and (key in existing_texts or key in seen_texts):
            problems.append("Doublon : énoncé identique déjà présent dans cette catégorie.")
            duplicate = True
        if problems:
            errors.append({"row": idx, "code": code, "message": " ".join(problems), "duplicate": duplicate,
                           "existing_id": existing_id if duplicate and existing_id and code not in seen_codes else None,
                           "data": [("" if v is None else str(v)) for v in row]})
            continue
        seen_codes.add(code)
        seen_texts.add(key)
        valid.append({"row": idx, "code": code, "category": category, "theme": theme, "subtheme": rec.get("subtheme", ""),
                      "difficulty": difficulty, "qtype": qtype, "text": text, "explanation": rec.get("explanation", ""),
                      "options": options, "correct": sorted(correct), "existing_id": existing_id, "image": image})
    return valid, errors, total, ["" if h is None else str(h) for h in raw_header]


def _write_choices(question, item):
    question.choices.all().delete()
    Choice.objects.bulk_create([Choice(question=question, label=lab, text=txt, is_correct=lab in item["correct"], order=i)
                                for i, (lab, txt) in enumerate(item["options"].items())])


@transaction.atomic
def import_questions(fileobj, school, user, filename, commit, quiz=None, update_existing=False, new_quiz_title="", images=None):
    """Analyse (commit=False) ou importe un fichier Excel.

    - quiz : questionnaire existant à alimenter avec les questions du fichier ;
    - new_quiz_title : crée un nouveau questionnaire (mode manuel) avec les questions du fichier ;
    - update_existing : les codes déjà présents sont mis à jour au lieu d'être rejetés comme doublons.
    """
    valid, errors, total, raw_header = analyse_workbook(fileobj, school, update_existing, images)
    imported = updated = 0
    ids = []
    if commit:
        for item in valid:
            fields = dict(category=item["category"], theme=item["theme"], subtheme=item["subtheme"], difficulty=item["difficulty"],
                          qtype=item["qtype"], text=item["text"], explanation=item["explanation"])
            if item.get("existing_id"):
                q = Question.objects.get(pk=item["existing_id"])
                for k, v in fields.items():
                    setattr(q, k, v)
                q.save()
                updated += 1
            else:
                q = Question.objects.create(school=school, code=item["code"], **fields)
                imported += 1
            _write_choices(q, item)
            if item.get("image"):
                from django.core.files.base import ContentFile
                data, name = item["image"]
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else "png"
                q.image.save(re.sub(r"[^A-Za-z0-9_-]+", "-", item["code"]) + "." + ext, ContentFile(data), save=True)
            ids.append(q.id)
        # doublons de code déjà en base : ils rejoignent quand même le questionnaire ciblé
        ids += [e["existing_id"] for e in errors if e.get("existing_id")]
        if new_quiz_title and ids:
            first = Question.objects.get(pk=ids[0])
            quiz = Quiz.objects.create(school=school, title=new_quiz_title, category=first.category, mode=Quiz.MANUAL)
        if quiz and ids:
            quiz.questions.add(*ids)
            quiz.mode = Quiz.MANUAL
            quiz.num_questions = quiz.questions.count()
            quiz.save(update_fields=["mode", "num_questions", "updated_at"])
    return ImportJob.objects.create(
        school=school, user=user, filename=filename, dry_run=not commit, total=total, valid=len(valid), imported=imported,
        updated=updated, quiz=quiz if commit else None, update_existing=update_existing,
        header=raw_header, duplicates=sum(1 for e in errors if e["duplicate"]), error_count=len(errors), errors=errors,
        preview=[{k: v[k] for k in ("row", "code", "category", "theme", "qtype", "text", "options", "correct")} | {"update": bool(v.get("existing_id")), "has_image": bool(v.get("image"))}
                 for v in valid[:20]])


def errors_workbook(job):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Erreurs"
    ws.append(["Ligne", "Erreur"] + list(job.header))
    for e in job.errors:
        ws.append([e["row"], e["message"]] + e["data"])
    return wb
