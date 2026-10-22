"""Génère/synchronise, pour chaque OfferTypeConfig (toutes les auto-écoles), le Plan individuel « attaché »
correspondant (vendable séparément depuis l'écran « mes demandes » du candidat, en plus des plans génériques
Découverte/Réussite… — décision produit purement additive).

    python manage.py sync_offer_type_plans

Idempotent : délègue à apps.admissions.services.sync_plan_for_offer_config (même logique que le hook de
synchronisation automatique de OfferTypeConfigViewSet.perform_create/perform_update — une seule source de
vérité pour le mapping config -> plan). Ré-exécutable à tout moment pour rattraper des configs créées hors
de l'admin (ex. seed_offer_type_configs) ou pour forcer une resynchronisation complète.
"""
from django.core.management.base import BaseCommand

from apps.admissions.models import OfferTypeConfig
from apps.admissions.services import sync_plan_for_offer_config


class Command(BaseCommand):
    help = ("Crée/actualise le Plan individuel correspondant à chaque OfferTypeConfig (tous les types de "
            "demande, toutes les auto-écoles). Idempotent.")

    def handle(self, *args, **opts):
        configs = list(OfferTypeConfig.objects.select_related("school"))
        if not configs:
            return self.stderr.write("Aucun OfferTypeConfig : lancez d'abord seed_offer_type_configs.")

        for config in configs:
            sync_plan_for_offer_config(config)

        self.stdout.write(self.style.SUCCESS(
            f"{len(configs)} plan(s) synchronisé(s) depuis les types de demande."))
