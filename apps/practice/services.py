from collections import defaultdict

from django.db.models import Q

from .models import CRITERIA, Evaluation, Lesson

ACQUIRED_THRESHOLD = 7  # note /10 à partir de laquelle une compétence est acquise


def find_conflicts(lesson):
    """Retourne la liste des ressources déjà réservées sur le créneau (empêche les doubles réservations)."""
    qs = Lesson.objects.filter(school_id=lesson.school_id, start__lt=lesson.end, end__gt=lesson.start).exclude(
        status="cancelled")
    if lesson.pk:
        qs = qs.exclude(pk=lesson.pk)
    conflicts = []
    checks = [("learner_id", "L'apprenant", "learner"), ("instructor_id", "Le moniteur", "instructor"),
              ("vehicle_id", "Le véhicule", "vehicle"), ("room_id", "La salle", "room")]
    for field, label, _ in checks:
        val = getattr(lesson, field)
        # les cours en salle peuvent réunir plusieurs apprenants : seule la salle/le moniteur bloquent
        if val is None or (lesson.kind == "theory" and field == "learner_id"):
            continue
        clash = qs.filter(**{field: val})
        if field == "room_id" and lesson.kind == "theory":
            clash = clash.exclude(kind="theory", cohort_id=lesson.cohort_id) if lesson.cohort_id else clash
        other = clash.first()
        if other:
            conflicts.append(f"{label} est déjà réservé de {other.start:%H:%M} à {other.end:%H:%M} (séance #{other.pk}).")
    return conflicts


def driving_log(learner):
    """Carnet de conduite numérique."""
    planned_total = learner.training.practical_hours if learner.training else 0
    done = sum(l.duration_hours for l in learner.lessons.filter(kind="practical", status="done"))
    scheduled = sum(l.duration_hours for l in learner.lessons.filter(kind="practical", status="planned"))
    evaluations = list(Evaluation.objects.filter(learner=learner).order_by("date"))
    latest = defaultdict(list)
    for ev in evaluations:
        for k, v in ev.scores.items():
            if v is not None:
                latest[k].append(float(v))
    labels = dict(CRITERIA)
    skills = []
    for key, vals in latest.items():
        last = vals[-1]
        skills.append({"criterion": key, "label": labels.get(key, key), "last_score": last,
                       "average": round(sum(vals) / len(vals), 1), "acquired": last >= ACQUIRED_THRESHOLD})
    return {
        "planned_hours": planned_total, "done_hours": round(done, 2), "scheduled_hours": round(scheduled, 2),
        "remaining_hours": round(max(planned_total - done, 0), 2),
        "progress_percent": round(min(done * 100 / planned_total, 100), 1) if planned_total else 0,
        "acquired_skills": [s for s in skills if s["acquired"]],
        "skills_to_improve": [s for s in skills if not s["acquired"]],
        "sessions": [{"id": l.id, "start": l.start, "end": l.end, "hours": l.duration_hours, "status": l.status,
                      "instructor": str(l.instructor) if l.instructor else None, "observations": l.observations}
                     for l in learner.lessons.filter(kind="practical").order_by("-start")[:50]],
    }
